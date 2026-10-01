"""Loopback-only HTTP adapter for cloud provider keys and cost estimates."""

from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from voz.application.estimate_cloud_cost import (
    EstimateCloudTranscription,
    EstimateError,
    EstimateFailureCode,
)
from voz.application.ports.cloud_providers import CloudProviderInfo
from voz.application.ports.provider_secrets import (
    ProviderSecretsPort,
    SecretsError,
    SecretsFailureCode,
)

_SECRETS_STATUS = {
    SecretsFailureCode.KEY_INVALID: 422,
    SecretsFailureCode.FILE_INSECURE: 409,
    SecretsFailureCode.FILE_INVALID: 409,
    SecretsFailureCode.WRITE_FAILED: 500,
}
_ESTIMATE_STATUS = {
    EstimateFailureCode.PROVIDER_NOT_FOUND: 404,
    EstimateFailureCode.MEDIA_NOT_FOUND: 404,
    EstimateFailureCode.DURATION_UNKNOWN: 409,
}


class ProviderView(BaseModel):
    id: str
    label: str
    privacy_url: str | None
    configured: bool
    cloud: bool = True


class ApiKeyBody(BaseModel):
    key: str


class EstimateView(BaseModel):
    minutes: float
    usd: float
    price_source: str
    price_date: str


def create_providers_router(
    secrets: ProviderSecretsPort,
    providers: Sequence[CloudProviderInfo | str],
    estimate: EstimateCloudTranscription | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/providers", tags=["providers"])
    # ponytail: a bare id is accepted (label = id, no privacy link) so callers
    # that only know ids keep working; the composition root passes full infos.
    known = tuple(
        CloudProviderInfo(item, item) if isinstance(item, str) else item
        for item in providers
    )

    def require_known(provider_id: str) -> None:
        if provider_id not in {item.id for item in known}:
            raise _error(404, "provider_not_found", "Unknown cloud provider.")

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
            raise _error(
                _SECRETS_STATUS[error.code], error.code, error.user_message
            ) from None
        return Response(status_code=204)

    def delete_key(provider_id: str) -> Response:
        require_known(provider_id)
        try:
            secrets.delete(provider_id)
        except SecretsError as error:
            raise _error(
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
                raise _error(
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


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )
