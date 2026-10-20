create or replace function ref.period_bounds_ok(
    fiscal_year_ending integer,
    period_span text,
    fiscal_quarter integer,
    period_start date,
    period_end date
) returns boolean
language plpgsql
immutable
as $$
declare
    start_year integer;
    expected_start date;
    expected_end date;
begin
    if period_span = 'life_to_date' then
        return fiscal_year_ending is null
            and fiscal_quarter is null
            and period_start is null
            and period_end is not null;
    end if;

    if fiscal_year_ending is null or period_start is null or period_end is null then
        return false;
    end if;

    start_year := fiscal_year_ending - 1;

    if period_span = 'q1' then
        expected_start := make_date(start_year, 4, 1);
        expected_end := make_date(start_year, 6, 30);
    elsif period_span = 'q1_q2' then
        expected_start := make_date(start_year, 4, 1);
        expected_end := make_date(start_year, 9, 30);
    elsif period_span = 'q1_q3' then
        expected_start := make_date(start_year, 4, 1);
        expected_end := make_date(start_year, 12, 31);
    elsif period_span in ('fiscal_year', 'forecast_fiscal_year') then
        expected_start := make_date(start_year, 4, 1);
        expected_end := make_date(fiscal_year_ending, 3, 31);
    elsif period_span = 'quarter' and fiscal_quarter = 1 then
        expected_start := make_date(start_year, 4, 1);
        expected_end := make_date(start_year, 6, 30);
    elsif period_span = 'quarter' and fiscal_quarter = 2 then
        expected_start := make_date(start_year, 7, 1);
        expected_end := make_date(start_year, 9, 30);
    elsif period_span = 'quarter' and fiscal_quarter = 3 then
        expected_start := make_date(start_year, 10, 1);
        expected_end := make_date(start_year, 12, 31);
    elsif period_span = 'quarter' and fiscal_quarter = 4 then
        expected_start := make_date(fiscal_year_ending, 1, 1);
        expected_end := make_date(fiscal_year_ending, 3, 31);
    else
        return false;
    end if;

    return period_start = expected_start and period_end = expected_end;
end;
$$;
