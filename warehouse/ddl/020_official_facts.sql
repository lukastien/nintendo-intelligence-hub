create table if not exists raw_official.unit_sales_disclosure (
    disclosure_id bigint generated always as identity primary key,
    source_document_id text not null,
    source_class text not null default 'official_ir',
    metric_code text not null,
    product_grain text not null,
    platform_code text not null,
    is_platform_aggregate boolean not null,
    is_platform_component boolean not null default false,
    parent_platform_code text,
    game_code text,
    region_code text not null,
    is_region_aggregate boolean not null default false,
    fiscal_year_ending integer,
    period_span text not null,
    fiscal_quarter integer,
    period_start date,
    period_end date not null,
    as_of_date date not null,
    value_units numeric(20, 4),
    source_unit_scale integer not null,
    source_value_as_printed numeric(20, 4),
    is_forecast boolean not null default false,
    is_additive_flow boolean not null default true,
    sales_basis text not null default 'sell_in',
    definition_note text,
    retrieved_at timestamptz,
    constraint ck_unit_source check (source_class = 'official_ir'),
    constraint ck_unit_grain check (
        product_grain in ('hardware', 'software_total', 'software_title')
    ),
    constraint ck_unit_game check (
        (product_grain = 'software_title' and game_code is not null)
        or (product_grain in ('hardware', 'software_total') and game_code is null)
    ),
    constraint ck_unit_span check (
        period_span in (
            'q1', 'q1_q2', 'q1_q3', 'fiscal_year', 'quarter',
            'life_to_date', 'forecast_fiscal_year'
        )
    ),
    constraint ck_unit_quarter_field check (
        (period_span = 'quarter' and fiscal_quarter between 1 and 4)
        or (period_span <> 'quarter' and fiscal_quarter is null)
    ),
    constraint ck_unit_forecast check (
        (period_span = 'forecast_fiscal_year' and is_forecast)
        or (period_span <> 'forecast_fiscal_year' and not is_forecast)
    ),
    constraint ck_unit_basis check (sales_basis = 'sell_in'),
    constraint ck_unit_scale check (source_unit_scale in (1, 1000, 10000, 1000000)),
    constraint ck_unit_normalization check (
        value_units is null
        or source_value_as_printed is null
        or value_units = source_value_as_printed * source_unit_scale
    ),
    constraint ck_unit_component check (
        (is_platform_component and parent_platform_code is not null)
        or (not is_platform_component and parent_platform_code is null)
    ),
    constraint ck_unit_dates check (
        ref.period_bounds_ok(
            fiscal_year_ending, period_span, fiscal_quarter, period_start, period_end
        )
    )
);

alter table raw_official.unit_sales_disclosure drop constraint if exists ck_unit_as_of;
alter table raw_official.unit_sales_disclosure
    add constraint ck_unit_as_of check (as_of_date >= period_end);

drop index if exists raw_official.uq_unit_sales_disclosure;
create unique index uq_unit_sales_disclosure
    on raw_official.unit_sales_disclosure (
        source_document_id,
        metric_code,
        platform_code,
        region_code,
        coalesce(game_code, ''),
        coalesce(fiscal_year_ending, 0),
        period_span,
        coalesce(fiscal_quarter, 0),
        is_forecast
    );

comment on table raw_official.unit_sales_disclosure is
'GRAIN: one Nintendo-disclosed sell-in measure as printed, for one source document, fiscal year (empty for life-to-date), metric, platform scope, region scope, optional title, and period span. Spans q1, q1_q2, q1_q3, and fiscal_year are cumulative from April 1. Span quarter is one fiscal quarter. life_to_date and forecast_fiscal_year stay on this table. value_units is the printed number multiplied by source_unit_scale. as_of_date is on or after period_end.';

create table if not exists raw_official.financial_line (
    financial_line_id bigint generated always as identity primary key,
    source_document_id text not null,
    source_class text not null default 'official_ir',
    metric_code text not null,
    entity_code text not null default 'nintendo_co_ltd_consolidated',
    platform_code text not null default 'CONSOLIDATED',
    region_code text not null,
    is_region_aggregate boolean not null default false,
    fiscal_year_ending integer,
    period_span text not null,
    fiscal_quarter integer,
    period_start date,
    period_end date not null,
    as_of_date date not null,
    amount_as_printed numeric(24, 4),
    printed_scale text not null,
    amount_yen numeric(24, 2),
    currency_code text not null default 'JPY',
    is_forecast boolean not null default false,
    is_additive_flow boolean not null,
    definition_note text,
    retrieved_at timestamptz,
    constraint ck_fin_source check (source_class = 'official_ir'),
    constraint ck_fin_entity check (entity_code = 'nintendo_co_ltd_consolidated'),
    constraint ck_fin_platform check (platform_code = 'CONSOLIDATED'),
    constraint ck_fin_currency check (currency_code = 'JPY'),
    constraint ck_fin_span check (
        period_span in (
            'q1', 'q1_q2', 'q1_q3', 'fiscal_year', 'quarter',
            'life_to_date', 'forecast_fiscal_year'
        )
    ),
    constraint ck_fin_quarter_field check (
        (period_span = 'quarter' and fiscal_quarter between 1 and 4)
        or (period_span <> 'quarter' and fiscal_quarter is null)
    ),
    constraint ck_fin_forecast check (
        (period_span = 'forecast_fiscal_year' and is_forecast)
        or (period_span <> 'forecast_fiscal_year' and not is_forecast)
    ),
    constraint ck_fin_scale check (
        printed_scale in ('ones', 'thousands', 'millions', 'billions')
    ),
    constraint ck_fin_normalization check (
        amount_yen is null
        or amount_as_printed is null
        or amount_yen = amount_as_printed * case printed_scale
            when 'ones' then 1
            when 'thousands' then 1000
            when 'millions' then 1000000
            when 'billions' then 1000000000
        end
    ),
    constraint ck_fin_dates check (
        ref.period_bounds_ok(
            fiscal_year_ending, period_span, fiscal_quarter, period_start, period_end
        )
    )
);

alter table raw_official.financial_line drop constraint if exists ck_fin_as_of;
alter table raw_official.financial_line
    add constraint ck_fin_as_of check (as_of_date >= period_end);

drop index if exists raw_official.uq_financial_line;
create unique index uq_financial_line
    on raw_official.financial_line (
        source_document_id,
        metric_code,
        region_code,
        coalesce(fiscal_year_ending, 0),
        period_span,
        coalesce(fiscal_quarter, 0),
        is_forecast
    );

comment on table raw_official.financial_line is
'GRAIN: one consolidated Nintendo Co., Ltd. statement amount as printed, for one source document, fiscal year (empty for life-to-date), metric, region scope, and period span. Year-to-date spans are cumulative from April 1. The incremental mart includes a row only when is_additive_flow and the metric catalog additive_flow are both true. amount_yen is the printed amount multiplied by printed_scale. as_of_date is on or after period_end.';
