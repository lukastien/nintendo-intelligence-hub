create table if not exists raw_simulated.weekly_sell_through (
    weekly_sell_through_id bigint generated always as identity primary key,
    source_class text not null default 'simulated_operational',
    series_name text not null,
    iso_year integer not null,
    iso_week integer not null,
    week_start date not null,
    sku_code text not null,
    region_code text not null,
    channel_code text not null,
    units integer not null,
    disclaimer text not null,
    loaded_at timestamptz not null default now(),
    constraint ck_sim_source check (source_class = 'simulated_operational'),
    constraint ck_sim_series check (series_name like 'synthetic_%'),
    constraint ck_sim_sku check (sku_code like 'SYN_%'),
    constraint ck_sim_region check (region_code like 'SIM_%'),
    constraint ck_sim_channel check (channel_code like 'SIM_%'),
    constraint ck_sim_units check (units >= 0),
    constraint ck_sim_disclaimer check (char_length(disclaimer) >= 40),
    constraint uq_sim_week unique (
        series_name, iso_year, iso_week, sku_code, region_code, channel_code
    )
);

comment on table raw_simulated.weekly_sell_through is
'GRAIN: one synthetic sell-through quantity per ISO week, synthetic SKU, synthetic region, and synthetic channel. These rows are generated for pipeline tests. They are not Nintendo disclosures, estimates, or sell-in.';
