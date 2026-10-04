"""Thin HTTP input adapter for creating and listing projects."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from voz.application.project_glossary import (
    MAX_GLOSSARY_TERMS,
    MAX_TERM_LENGTH,
    InvalidGlossary,
    ProjectGlossary,
    ProjectNotFound,
)
from voz.application.projects import (
    CreateProject,
    DeleteProject,
    InvalidProjectName,
    ListProjects,
    ProjectBusy,
    ProjectDeleteFailed,
    RenameProject,
)
from voz.domain.entities.project import Project


class CreateProjectRequest(BaseModel):
    name: str


DELETE_HEADER = "X-VOZ-Action"
DELETE_VALUE = "delete-project"


class RenameProjectRequest(BaseModel):
    name: str


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime

    @classmethod
    def from_entity(cls, project: Project) -> "ProjectResponse":
        return cls(id=project.id, name=project.name, created_at=project.created_at)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


class GlossaryRequest(BaseModel):
    terms: list[str]


class GlossaryResponse(BaseModel):
    terms: list[str]
    max_terms: int
    max_term_length: int
    applies_to: list[str]
    """Provider ids that use the glossary; every other engine ignores it."""


def _glossary_response(
    terms: tuple[str, ...], providers: tuple[str, ...]
) -> GlossaryResponse:
    return GlossaryResponse(
        terms=list(terms),
        max_terms=MAX_GLOSSARY_TERMS,
        max_term_length=MAX_TERM_LENGTH,
        applies_to=list(providers),
    )


def create_projects_router(
    create: CreateProject,
    list_projects: ListProjects,
    glossary: ProjectGlossary | None = None,
    rename: RenameProject | None = None,
    delete: DeleteProject | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["projects"])

    def create_project(body: CreateProjectRequest) -> ProjectResponse:
        try:
            project = create.execute(name=body.name)
        except InvalidProjectName as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "project_name_invalid", "message": str(error)},
            ) from None
        return ProjectResponse.from_entity(project)

    def get_projects() -> ProjectListResponse:
        return ProjectListResponse(
            projects=[
                ProjectResponse.from_entity(project)
                for project in list_projects.execute()
            ]
        )

    router.add_api_route(
        "/projects",
        create_project,
        methods=["POST"],
        status_code=201,
        response_model=ProjectResponse,
    )
    router.add_api_route(
        "/projects",
        get_projects,
        methods=["GET"],
        response_model=ProjectListResponse,
    )

    def not_found() -> HTTPException:
        return HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": "The project does not exist.",
            },
        )

    if rename is not None:
        renamer = rename

        def patch_project(
            project_id: UUID, body: RenameProjectRequest
        ) -> ProjectResponse:
            try:
                return ProjectResponse.from_entity(
                    renamer.execute(project_id, body.name)
                )
            except ProjectNotFound:
                raise not_found() from None
            except InvalidProjectName as error:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "project_name_invalid", "message": str(error)},
                ) from None

        router.add_api_route(
            "/projects/{project_id}",
            patch_project,
            methods=["PATCH"],
            response_model=ProjectResponse,
        )
    if delete is not None:
        eraser = delete

        def delete_project(
            project_id: UUID,
            action: str | None = Header(default=None, alias=DELETE_HEADER),
        ) -> None:
            if action != DELETE_VALUE:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "project_delete_forbidden",
                        "message": f"Send the header {DELETE_HEADER}: {DELETE_VALUE}.",
                    },
                )
            try:
                eraser.execute(project_id)
            except ProjectNotFound:
                raise not_found() from None
            except ProjectBusy:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "project_busy",
                        "message": "A job of this project is still running. "
                        "Cancel it or wait for it to finish.",
                    },
                ) from None
            except ProjectDeleteFailed:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": "project_delete_failed",
                        "message": "The project files could not be deleted. "
                        "Nothing was removed; try again.",
                    },
                ) from None

        router.add_api_route(
            "/projects/{project_id}",
            delete_project,
            methods=["DELETE"],
            status_code=204,
        )
    if glossary is not None:
        service = glossary

        def get_glossary(project_id: UUID) -> GlossaryResponse:
            try:
                return _glossary_response(service.get(project_id), service.providers)
            except ProjectNotFound:
                raise not_found() from None

        def put_glossary(project_id: UUID, body: GlossaryRequest) -> GlossaryResponse:
            try:
                return _glossary_response(
                    service.replace(project_id, body.terms), service.providers
                )
            except ProjectNotFound:
                raise not_found() from None
            except InvalidGlossary as error:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "glossary_invalid", "message": str(error)},
                ) from None

        router.add_api_route(
            "/projects/{project_id}/glossary",
            get_glossary,
            methods=["GET"],
            response_model=GlossaryResponse,
        )
        router.add_api_route(
            "/projects/{project_id}/glossary",
            put_glossary,
            methods=["PUT"],
            response_model=GlossaryResponse,
        )
    return router
