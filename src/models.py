from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class PersonalInfo(BaseModel):
    name: str
    email: str
    phone: str
    location: str
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None


class Experience(BaseModel):
    title: str
    company: str
    location: str
    start_date: str
    end_date: str          # "Actualidad" si es trabajo actual
    achievements: List[str]


class Education(BaseModel):
    degree: str
    institution: str
    location: str
    start_date: str
    end_date: str
    gpa: Optional[str] = None
    relevant_courses: Optional[List[str]] = None


class Project(BaseModel):
    name: str
    description: str
    technologies: List[str]
    url: Optional[str] = None
    github: Optional[str] = None


class Skills(BaseModel):
    technical: List[str]
    soft: List[str]
    languages: List[str]   # "Español (nativo)", "Inglés (B2)"
    tools: List[str]


class CV(BaseModel):
    personal: PersonalInfo
    summary: str
    experience: List[Experience]
    education: List[Education]
    skills: Skills
    projects: List[Project]
    certifications: Optional[List[str]] = None


class JobAnalysis(BaseModel):
    title: str
    company: str
    required_skills: List[str]
    preferred_skills: List[str]
    soft_skills: List[str]
    ats_keywords: List[str]
    experience_level: str          # Junior | Mid | Senior
    key_responsibilities: List[str]
    company_culture: Optional[str] = None
    match_score: int               # 0–100 calculado vs CV base
    gaps: List[str]                # habilidades faltantes
    highlights: List[str]          # qué enfatizar del CV
