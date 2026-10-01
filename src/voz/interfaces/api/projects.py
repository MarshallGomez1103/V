"""Thin HTTP input adapter for creating and listing projects."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from voz.application.project_glossary import (
    MAX_GLOSSARY_TERMS,
    MAX_TERM_LENGTH,
    InvalidGlossary,
    ProjectGlossary,
    ProjectNotFound,
)
from voz.application.projects import CreateProject, InvalidProjectName, ListProjects
from voz.domain.entities.project import Project


class CreateProjectRequest(BaseModel):
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
    if glossary is not None:
        service = glossary

        def not_found() -> HTTPException:
            return HTTPException(
                status_code=404,
                detail={
                    "code": "project_not_found",
                    "message": "The project does not exist.",
                },
            )

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
