"""Loopback-only HTTP adapter for cloud provider keys, cost estimates and
OpenAI-compatible endpoints (V4-04)."""

from collections.abc import Callable, Coroutine, Sequence
from typing import Any, Final
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from voz.application.estimate_cloud_cost import (
    EstimateCloudTranscription,
    EstimateError,
    EstimateFailureCode,
)
from voz.application.ports.cloud_providers import CloudProviderInfo
from voz.application.ports.compatible_endpoints import (
    CompatibleEndpoint,
    CompatibleEndpointStore,
    EndpointConnectionTester,
    EndpointError,
    EndpointFailureCode,
    is_loopback_url,
)
from voz.application.ports.provider_secrets import (
    ProviderSecretsPort,
    SecretsError,
    SecretsFailureCode,
)
from voz.interfaces.api.errors import api_error

_SECRETS_STATUS = {
    SecretsFailureCode.KEY_INVALID: 422,
    SecretsFailureCode.FILE_INSECURE: 409,
    SecretsFailureCode.FILE_INVALID: 409,
    SecretsFailureCode.WRITE_FAILED: 500,
}
_ENDPOINT_STATUS = {
    EndpointFailureCode.INVALID: 422,
    EndpointFailureCode.CONSENT_REQUIRED: 422,
    EndpointFailureCode.NOT_FOUND: 404,
    EndpointFailureCode.FILE_INSECURE: 409,
    EndpointFailureCode.FILE_INVALID: 409,
    EndpointFailureCode.WRITE_FAILED: 500,
}
ACTION_HEADER: Final = "X-VOZ-Action"
DELETE_ENDPOINT_ACTION: Final = "delete-compatible-endpoint"
_ESTIMATE_STATUS = {
    EstimateFailureCode.PROVIDER_NOT_FOUND: 404,
    EstimateFailureCode.MEDIA_NOT_FOUND: 404,
    EstimateFailureCode.DURATION_UNKNOWN: 409,
}


class _PrivateProviderRoute(APIRoute):
    """Validation failures must not echo credentials or other request values."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def private_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                raise api_error(
                    422, "endpoint_invalid", "The provider request is not valid."
                ) from None

        return private_handler


class ProviderView(BaseModel):
    id: str
    label: str
    privacy_url: str | None
    configured: bool
    cloud: bool = True


class ApiKeyBody(BaseModel):
    key: str


class EndpointBody(BaseModel):
    """Create/replace an endpoint. ``key``: ``None`` keeps, a value replaces."""

    name: str = Field(max_length=200)
    base_url: str = Field(max_length=1024)
    key: str | None = Field(default=None, max_length=1024)
    clear_key: bool = False
    stt_models: list[str] = Field(default_factory=list[str], max_length=64)
    tts_models: list[str] = Field(default_factory=list[str], max_length=64)
    tts_voices: list[str] = Field(default_factory=list[str], max_length=128)
    cloud_consent: bool = False


class EndpointView(BaseModel):
    id: str
    name: str
    base_url: str
    cloud: bool
    cloud_consent: bool
    key_configured: bool
    stt_models: list[str]
    tts_models: list[str]
    tts_voices: list[str]


class ConnectionView(BaseModel):
    reachable: bool
    status: int | None
    models: list[str]
    code: str | None


class EstimateView(BaseModel):
    minutes: float
    usd: float
    price_source: str
    price_date: str


def _endpoint_error(error: EndpointError) -> Exception:
    return api_error(_ENDPOINT_STATUS[error.code], error.code, error.user_message)


def _secrets_error(error: SecretsError) -> Exception:
    return api_error(_SECRETS_STATUS[error.code], error.code, error.user_message)


def _add_endpoint_routes(
    router: APIRouter,
    secrets: ProviderSecretsPort,
    store: CompatibleEndpointStore,
    tester: EndpointConnectionTester | None,
) -> None:
    """``/api/providers/compatible``: list, create, replace, delete, test."""

    def view(endpoint: CompatibleEndpoint) -> EndpointView:
        return EndpointView(
            id=endpoint.id,
            name=endpoint.name,
            base_url=endpoint.base_url,
            cloud=endpoint.cloud,
            cloud_consent=endpoint.cloud_consent,
            key_configured=secrets.configured(endpoint.secret_id),
            stt_models=list(endpoint.stt_models),
            tts_models=list(endpoint.tts_models),
            tts_voices=list(endpoint.tts_voices),
        )

    def existing(endpoint_id: str) -> CompatibleEndpoint:
        try:
            found = store.get(endpoint_id)
        except EndpointError as error:
            raise _endpoint_error(error) from None
        if found is None:
            raise api_error(
                404,
                EndpointFailureCode.NOT_FOUND,
                "The OpenAI-compatible server does not exist.",
            )
        return found

    def save(endpoint_id: str, body: EndpointBody) -> EndpointView:
        try:
            endpoint = CompatibleEndpoint(
                id=endpoint_id,
                name=body.name.strip(),
                base_url=body.base_url,
                stt_models=tuple(item.strip() for item in body.stt_models),
                tts_models=tuple(item.strip() for item in body.tts_models),
                tts_voices=tuple(item.strip() for item in body.tts_voices),
                # Consent belongs to a non-loopback URL; a local one records none.
                cloud_consent=body.cloud_consent
                and not is_loopback_url(body.base_url.strip()),
            )
            # Key first: a rejected key leaves no half-saved endpoint behind.
            if body.key is not None and body.key.strip():
                secrets.set(endpoint.secret_id, body.key.strip())
            elif body.clear_key:
                secrets.delete(endpoint.secret_id)
            store.save(endpoint)
        except EndpointError as error:
            raise _endpoint_error(error) from None
        except SecretsError as error:
            raise _secrets_error(error) from None
        return view(endpoint)

    def list_endpoints() -> list[EndpointView]:
        try:
            return [view(item) for item in store.list()]
        except EndpointError as error:
            raise _endpoint_error(error) from None

    async def get_endpoints() -> list[EndpointView]:
        return await run_in_threadpool(list_endpoints)

    async def post_endpoint(body: EndpointBody) -> EndpointView:
        return await run_in_threadpool(save, uuid4().hex[:12], body)

    def replace(endpoint_id: str, body: EndpointBody) -> EndpointView:
        existing(endpoint_id)
        return save(endpoint_id, body)

    async def put_endpoint(endpoint_id: str, body: EndpointBody) -> EndpointView:
        return await run_in_threadpool(replace, endpoint_id, body)

    def remove(endpoint_id: str) -> None:
        endpoint = existing(endpoint_id)
        try:
            secrets.delete(endpoint.secret_id)
            store.delete(endpoint_id)
        except EndpointError as error:
            raise _endpoint_error(error) from None
        except SecretsError as error:
            raise _secrets_error(error) from None

    async def delete_endpoint(
        endpoint_id: str,
        action: str | None = Header(default=None, alias=ACTION_HEADER),
    ) -> Response:
        if action != DELETE_ENDPOINT_ACTION:
            raise api_error(
                403,
                "endpoint_delete_forbidden",
                f"Send the header {ACTION_HEADER}: {DELETE_ENDPOINT_ACTION}.",
            )
        await run_in_threadpool(remove, endpoint_id)
        return Response(status_code=204)

    def check(endpoint_id: str) -> ConnectionView:
        endpoint = existing(endpoint_id)
        if tester is None:
            raise api_error(
                501, "endpoint_test_unavailable", "Connection tests are not wired."
            )
        try:
            key = secrets.get(endpoint.secret_id)
        except SecretsError as error:
            raise _secrets_error(error) from None
        # Only saved endpoints are tested: a cloud one already carries consent.
        result = tester.check(endpoint, key)
        return ConnectionView(
            reachable=result.reachable,
            status=result.status,
            models=list(result.models),
            code=result.code,
        )

    async def test_endpoint(endpoint_id: str) -> ConnectionView:
        return await run_in_threadpool(check, endpoint_id)

    base = "/compatible"
    router.add_api_route(base, get_endpoints, methods=["GET"])
    router.add_api_route(base, post_endpoint, methods=["POST"], status_code=201)
    router.add_api_route(base + "/{endpoint_id}", put_endpoint, methods=["PUT"])
    router.add_api_route(
        base + "/{endpoint_id}", delete_endpoint, methods=["DELETE"], status_code=204
    )
    router.add_api_route(base + "/{endpoint_id}/test", test_endpoint, methods=["POST"])


def create_providers_router(
    secrets: ProviderSecretsPort,
    providers: Sequence[CloudProviderInfo | str],
    estimate: EstimateCloudTranscription | None = None,
    *,
    endpoints: CompatibleEndpointStore | None = None,
    tester: EndpointConnectionTester | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/providers", tags=["providers"], route_class=_PrivateProviderRoute
    )
    if endpoints is not None:  # before ``/{provider_id}/...``: literal path first
        _add_endpoint_routes(router, secrets, endpoints, tester)
    # ponytail: a bare id is accepted (label = id, no privacy link) so callers
    # that only know ids keep working; the composition root passes full infos.
    known = tuple(
        CloudProviderInfo(item, item) if isinstance(item, str) else item
        for item in providers
    )

    def require_known(provider_id: str) -> None:
        if provider_id not in {item.id for item in known}:
            raise api_error(404, "provider_not_found", "Unknown cloud provider.")

    def list_providers() -> list[ProviderView]:
        return [
            ProviderView(
                id=item.id,
                label=item.label,
                privacy_url=item.privacy_url,
                configured=secrets.configured(item.id),
            )
            for item in known
        ]

    def put_key(provider_id: str, body: ApiKeyBody) -> Response:
        require_known(provider_id)
        try:
            secrets.set(provider_id, body.key)
        except SecretsError as error:
            raise api_error(
                _SECRETS_STATUS[error.code], error.code, error.user_message
            ) from None
        return Response(status_code=204)

    def delete_key(provider_id: str) -> Response:
        require_known(provider_id)
        try:
            secrets.delete(provider_id)
        except SecretsError as error:
            raise api_error(
                _SECRETS_STATUS[error.code], error.code, error.user_message
            ) from None
        return Response(status_code=204)

    router.add_api_route("", list_providers, methods=["GET"])
    router.add_api_route(
        "/{provider_id}/key", put_key, methods=["PUT"], status_code=204
    )
    router.add_api_route(
        "/{provider_id}/key", delete_key, methods=["DELETE"], status_code=204
    )

    if estimate is not None:
        use_case = estimate

        def get_estimate(
            provider_id: str, media_asset_id: UUID, model: str | None = None
        ) -> EstimateView:
            require_known(provider_id)
            try:
                result = use_case.execute(provider_id, media_asset_id, model)
            except EstimateError as error:
                raise api_error(
                    _ESTIMATE_STATUS[error.code], error.code, error.user_message
                ) from None
            return EstimateView(
                minutes=result.minutes,
                usd=result.usd,
                price_source=result.price_source,
                price_date=result.price_date,
            )

        router.add_api_route("/{provider_id}/estimate", get_estimate, methods=["GET"])
    return router
