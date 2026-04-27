-- Chainlit 2.10.1 schema initialisation
-- Creates a dedicated "chainlit" schema so Chainlit's tables do not collide
-- with the application's own "public" schema tables.
--
-- Usage:
--   psql $DATABASE_URL -f scripts/chainlit_schema_init.sql

CREATE SCHEMA IF NOT EXISTS chainlit;

CREATE TABLE IF NOT EXISTS chainlit."User" (
    id          TEXT        PRIMARY KEY,
    identifier  TEXT        NOT NULL UNIQUE,
    metadata    TEXT        NOT NULL DEFAULT '{}',
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chainlit."Thread" (
    id          TEXT        PRIMARY KEY,
    name        TEXT,
    "userId"    TEXT,
    metadata    TEXT        NOT NULL DEFAULT '{}',
    tags        TEXT[],
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "deletedAt" TIMESTAMPTZ,
    FOREIGN KEY ("userId") REFERENCES chainlit."User"(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_thread_userid  ON chainlit."Thread" ("userId");
CREATE INDEX IF NOT EXISTS idx_thread_updated ON chainlit."Thread" ("updatedAt" DESC);

CREATE TABLE IF NOT EXISTS chainlit."Step" (
    id          TEXT        PRIMARY KEY,
    "threadId"  TEXT,
    "parentId"  TEXT,
    name        TEXT,
    type        TEXT        NOT NULL DEFAULT 'run',
    input       TEXT,
    output      TEXT,
    metadata    TEXT        NOT NULL DEFAULT '{}',
    "showInput" TEXT,
    "isError"   BOOLEAN     NOT NULL DEFAULT FALSE,
    "startTime" TIMESTAMPTZ,
    "endTime"   TIMESTAMPTZ,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY ("threadId") REFERENCES chainlit."Thread"(id) ON DELETE CASCADE,
    FOREIGN KEY ("parentId") REFERENCES chainlit."Step"(id)   ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_step_threadid  ON chainlit."Step" ("threadId");
CREATE INDEX IF NOT EXISTS idx_step_starttime ON chainlit."Step" ("startTime");

CREATE TABLE IF NOT EXISTS chainlit."Element" (
    id              TEXT    PRIMARY KEY,
    "threadId"      TEXT,
    "stepId"        TEXT,
    metadata        TEXT    NOT NULL DEFAULT '{}',
    mime            TEXT,
    name            TEXT,
    "objectKey"     TEXT,
    url             TEXT,
    "chainlitKey"   TEXT,
    display         TEXT,
    size            TEXT,
    language        TEXT,
    page            INTEGER,
    props           TEXT    NOT NULL DEFAULT '{}',
    FOREIGN KEY ("threadId") REFERENCES chainlit."Thread"(id) ON DELETE CASCADE,
    FOREIGN KEY ("stepId")   REFERENCES chainlit."Step"(id)   ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_element_threadid ON chainlit."Element" ("threadId");
CREATE INDEX IF NOT EXISTS idx_element_stepid   ON chainlit."Element" ("stepId");

CREATE TABLE IF NOT EXISTS chainlit."Feedback" (
    id          TEXT    PRIMARY KEY,
    "stepId"    TEXT    NOT NULL,
    name        TEXT    NOT NULL DEFAULT 'user_feedback',
    value       FLOAT   NOT NULL,
    comment     TEXT,
    FOREIGN KEY ("stepId") REFERENCES chainlit."Step"(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_feedback_stepid ON chainlit."Feedback" ("stepId");
