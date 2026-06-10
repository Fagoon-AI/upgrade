-- Migration: create llm_model_configs table
-- Date: 2026-06-10

-- NOTE: This project does not have Alembic configured. Run this SQL directly against your Postgres database.
-- Ensure the "pgcrypto" extension is enabled for gen_random_uuid(), or remove DEFAULT gen_random_uuid() and provide UUIDs from the application.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS llm_model_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT,
    provider TEXT NOT NULL,
    model_id TEXT,
    api_key TEXT,
    features JSONB DEFAULT '[]'::jsonb,
    agent_ids JSONB DEFAULT '[]'::jsonb,
    workflow_ids JSONB DEFAULT '[]'::jsonb,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Foreign key to users table (assumes users table exists with id UUID primary key)
ALTER TABLE llm_model_configs
    ADD CONSTRAINT fk_llm_model_configs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_llm_model_configs_user_id ON llm_model_configs(user_id);

-- Trigger to update updated_at on row modification
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_timestamp ON llm_model_configs;
CREATE TRIGGER set_timestamp
BEFORE UPDATE ON llm_model_configs
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();
