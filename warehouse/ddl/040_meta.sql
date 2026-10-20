create table if not exists meta.source_document (
    source_document_id text primary key,
    source_class text not null,
    publisher_name text not null,
    title text not null,
    published_on date,
    source_url text,
    period_label_verbatim text,
    content_sha256 text,
    retrieved_at timestamptz,
    constraint ck_doc_class check (
        source_class in ('official_ir', 'public_reference', 'simulated_operational')
    ),
    constraint ck_doc_official check (
        source_class <> 'official_ir' or publisher_name = 'Nintendo Co., Ltd.'
    ),
    constraint ck_doc_simulated check (
        source_class <> 'simulated_operational' or publisher_name = 'SYNTHETIC'
    )
);

comment on table meta.source_document is
'GRAIN: one row per retrieved document or synthetic generator run. Official rows keep the verbatim period label from the publication.';

create table if not exists meta.load_audit (
    load_audit_id bigint generated always as identity primary key,
    loaded_at timestamptz not null default now(),
    action text not null,
    row_count integer,
    note text not null
);

comment on table meta.load_audit is
'GRAIN: one row per warehouse bootstrap or load action. This is a control table, not a sales fact.';
