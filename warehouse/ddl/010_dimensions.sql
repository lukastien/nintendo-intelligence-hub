create table if not exists ref.dim_platform (
    platform_code text primary key,
    platform_name text not null,
    family_code text not null,
    is_aggregate boolean not null,
    is_component boolean not null,
    parent_platform_code text,
    hardware_form text not null,
    reference_note text not null,
    constraint ck_platform_role check (is_aggregate <> is_component or (not is_aggregate and not is_component)),
    constraint ck_platform_parent check (
        (is_component and parent_platform_code is not null)
        or (not is_component and parent_platform_code is null)
    )
);

comment on table ref.dim_platform is
'GRAIN: one row per platform scope used on a disclosure. Aggregate families and their component models are separate rows. This dimension stores names only.';

create table if not exists ref.dim_region (
    region_code text primary key,
    region_name text not null,
    is_aggregate boolean not null,
    aggregate_note text not null,
    sort_order integer not null
);

comment on table ref.dim_region is
'GRAIN: one row per Nintendo IR geography, plus GLOBAL for a worldwide total. The Americas is a consolidated sales region.';

create table if not exists ref.dim_game (
    game_code text primary key,
    title text not null,
    franchise_code text,
    publisher_role text not null,
    source_class text not null default 'public_reference',
    source_url text,
    notes text,
    constraint ck_game_role check (publisher_role in ('first_party', 'third_party', 'unknown')),
    constraint ck_game_source check (source_class = 'public_reference')
);

comment on table ref.dim_game is
'GRAIN: one row per game identifier. Titles are public reference attributes. This table stores no sales.';

create table if not exists ref.bridge_game_platform (
    game_code text not null references ref.dim_game (game_code),
    platform_code text not null references ref.dim_platform (platform_code),
    primary key (game_code, platform_code)
);

comment on table ref.bridge_game_platform is
'GRAIN: one row per game and platform compatibility. Reference data only. It stores no sales.';

create table if not exists ref.dim_metric (
    metric_code text primary key,
    metric_name text not null,
    measure_family text not null,
    additive_flow boolean not null,
    native_unit text not null,
    sales_basis text not null,
    statement_scope text not null,
    comparability_note text not null,
    constraint ck_metric_family check (
        measure_family in ('unit_sales', 'income_statement', 'balance_sheet')
    ),
    constraint ck_metric_flow check (
        measure_family <> 'balance_sheet' or additive_flow = false
    )
);

comment on table ref.dim_metric is
'GRAIN: one row per metric definition. The catalog stores meaning and additivity, not amounts.';

create table if not exists ref.dim_date (
    date_key integer primary key,
    calendar_date date not null unique,
    calendar_year integer not null,
    calendar_month integer not null,
    calendar_quarter integer not null,
    iso_year integer not null,
    iso_week integer not null,
    nintendo_fiscal_year_ending integer not null,
    fiscal_label text not null,
    fiscal_quarter integer not null,
    fiscal_quarter_start date not null,
    fiscal_quarter_end date not null,
    is_fiscal_quarter_end boolean not null,
    fiscal_year_start date not null,
    fiscal_year_end date not null
);

comment on table ref.dim_date is
'GRAIN: one row per calendar date. Fiscal attributes follow the year ending March 31. This dimension stores no measures.';
