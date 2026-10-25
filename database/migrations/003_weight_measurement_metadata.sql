-- Retain authoritative measurement provenance until analysis; copied to inspections.notes.
-- Apply once to existing databases before deploying the Weight-stage update.
ALTER TABLE pending_transactions ADD COLUMN weight_metadata TEXT NULL;
