-- Add signed column for autographed/inscribed books
ALTER TABLE books ADD COLUMN signed INTEGER DEFAULT 0;
