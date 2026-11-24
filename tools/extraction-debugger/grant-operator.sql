-- Invoke as the schema administrator with psql -v debugger_operator=operator_login.
GRANT CONNECT ON DATABASE :"DBNAME" TO :"debugger_operator";
GRANT USAGE ON SCHEMA public TO :"debugger_operator";
GRANT SELECT ON public.extraction_response_audits TO :"debugger_operator";
GRANT INSERT (work_unit_id) ON public.extraction_response_audit_reads TO :"debugger_operator";
GRANT SELECT (id, original_filename) ON public.documents TO :"debugger_operator";
GRANT SELECT (id, page_number) ON public.document_pages TO :"debugger_operator";
GRANT SELECT (id, document_id, provider, model) ON public.extraction_runs TO :"debugger_operator";
GRANT SELECT (id, run_id, execution_metadata, attempt_number, finished_at, status, stage, performance,
    output_counts, error_code) ON public.extraction_work_units TO :"debugger_operator";
GRANT SELECT (work_unit_id, duration_ms, input_tokens, output_tokens, cached_input_tokens,
    estimated_cost_usd, pricing_basis, schema_version, prompt_version, validation_diagnostics)
    ON public.extraction_ai_calls TO :"debugger_operator";
GRANT SELECT (work_unit_id, request_hash, result_hash, upstream_hash, payload)
    ON public.extraction_stage_results TO :"debugger_operator";
GRANT SELECT (id, ordinal, local_ref, mapping_status, reason_code, normalized_type,
    normalized_unit, value_number, value_integer, value_text, value_boolean, work_unit_id, kind,
    proposed_value, alternate_representations)
    ON public.extraction_candidates TO :"debugger_operator";
GRANT SELECT (candidate_id, role, localization, reason_code, ordinal) ON public.extraction_evidence
    TO :"debugger_operator";
