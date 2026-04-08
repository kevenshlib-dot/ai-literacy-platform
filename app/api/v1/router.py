from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, users, materials, questions, papers, exams, scores, sessions, interactive, annotations, indicators, reports, organizations, courses, learning, sandbox, closed_loop, system_config

api_router = APIRouter()

api_router.include_router(health.router, tags=["健康检查"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(materials.router)
api_router.include_router(questions.router)
api_router.include_router(papers.router)
api_router.include_router(exams.router)
api_router.include_router(scores.router)
api_router.include_router(sessions.router)
api_router.include_router(interactive.router)
api_router.include_router(annotations.router)
api_router.include_router(indicators.router)
api_router.include_router(reports.router)
api_router.include_router(organizations.router)
api_router.include_router(courses.router)
api_router.include_router(learning.router)
api_router.include_router(sandbox.router)
api_router.include_router(closed_loop.router)
api_router.include_router(system_config.router)
