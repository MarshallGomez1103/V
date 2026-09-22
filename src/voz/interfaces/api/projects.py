"""Thin HTTP input adapter for creating and listing projects."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


def create_projects_router(
    create: CreateProject, list_projects: ListProjects
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
    return router
