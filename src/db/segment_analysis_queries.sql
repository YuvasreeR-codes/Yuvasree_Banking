
-- ============================================================
-- BANKING LOAN RISK ANALYSIS
-- STEP 13.4 - SEGMENT ANALYSIS AND BUSINESS RULE REVIEW
-- ============================================================


-- ============================================================
-- REPORT 1: CUSTOMER SEGMENT RISK ANALYSIS
--
-- Compare age, gender, education and marital segments.
-- Uses existing ETL-transformed labels.
-- ============================================================

WITH customer_segments AS (

    SELECT
        c.customer_id,
        'AGE_GROUP' AS segment_type,
        c.age_group AS segment_value
    FROM customers c

    UNION ALL

    SELECT
        c.customer_id,
        'GENDER',
        c.gender_label
    FROM customers c

    UNION ALL

    SELECT
        c.customer_id,
        'EDUCATION',
        c.education_label
    FROM customers c

    UNION ALL

    SELECT
        c.customer_id,
        'MARITAL_STATUS',
        c.marriage_label
    FROM customers c
)

SELECT
    s.segment_type,
    s.segment_value,

    COUNT(*) AS total_customers,

    ROUND(
        AVG(r.risk_score), 2
    ) AS average_risk_score,

    SUM(
        CASE WHEN r.risk_band = 'HIGH'
        THEN 1 ELSE 0 END
    ) AS high_risk_customers,

    ROUND(
        100.0 * SUM(
            CASE WHEN r.risk_band = 'HIGH'
            THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS high_risk_percentage,

    ROUND(
        AVG(cp.months_with_delay), 2
    ) AS average_delayed_months,

    ROUND(
        100.0 * AVG(cp.default_next_month),
        2
    ) AS historical_default_rate_pct

FROM customer_segments s

JOIN credit_profiles cp
    ON s.customer_id = cp.customer_id

JOIN customer_risk_scores r
    ON s.customer_id = r.customer_id

GROUP BY
    s.segment_type,
    s.segment_value

ORDER BY
    s.segment_type,
    high_risk_percentage DESC;


-- ============================================================
-- REPORT 2: CREDIT LIMIT AND PAYMENT BEHAVIOR BY SEGMENT
--
-- Compare credit exposure, bills, and repayments.
-- Uses age groups as the primary segment.
-- ============================================================

SELECT
    c.age_group,

    COUNT(*) AS total_customers,

    ROUND(
        AVG(cp.credit_limit), 2
    ) AS average_credit_limit,

    ROUND(
        SUM(cp.credit_limit), 2
    ) AS total_credit_limit_exposure,

    ROUND(
        AVG(cp.total_bill_amount), 2
    ) AS average_total_bill_amount,

    ROUND(
        AVG(cp.total_payment_amount), 2
    ) AS average_total_payment_amount,

    ROUND(
        SUM(cp.total_payment_amount) /
        NULLIF(
            SUM(
                CASE
                    WHEN cp.total_bill_amount > 0
                    THEN cp.total_bill_amount
                    ELSE 0
                END
            ), 0
        ),
        4
    ) AS payment_to_positive_bill_ratio,

    ROUND(
        AVG(cp.months_with_delay), 2
    ) AS average_delayed_months,

    ROUND(
        AVG(r.risk_score), 2
    ) AS average_risk_score

FROM customers c

JOIN credit_profiles cp
    ON c.customer_id = cp.customer_id

JOIN customer_risk_scores r
    ON c.customer_id = r.customer_id

GROUP BY c.age_group

ORDER BY MIN(c.age);


-- ============================================================
-- REPORT 3: RECORDS REQUIRING ADDITIONAL REVIEW
--
-- Business rules:
-- 1. HIGH risk band
-- 2. Maximum repayment delay >= 2 months
-- 3. Delayed payments in >= 3 months
-- 4. Latest credit utilization >= 80%
--
-- A record is flagged when ANY rule is satisfied.
-- ============================================================

WITH review_candidates AS (

    SELECT
        c.customer_id,
        c.age_group,

        cp.credit_limit,
        cp.max_repayment_delay,
        cp.months_with_delay,
        cp.latest_credit_utilization,
        cp.payment_to_bill_ratio,

        r.risk_score,
        r.risk_band,
        r.risk_reason,

        CASE
            WHEN r.risk_band = 'HIGH'
            THEN 1 ELSE 0
        END AS high_risk_flag,

        CASE
            WHEN cp.max_repayment_delay >= 2
            THEN 1 ELSE 0
        END AS serious_delay_flag,

        CASE
            WHEN cp.months_with_delay >= 3
            THEN 1 ELSE 0
        END AS repeated_delay_flag,

        CASE
            WHEN cp.latest_credit_utilization >= 0.80
            THEN 1 ELSE 0
        END AS high_utilization_flag

    FROM customers c

    JOIN credit_profiles cp
        ON c.customer_id = cp.customer_id

    JOIN customer_risk_scores r
        ON c.customer_id = r.customer_id
)

SELECT
    customer_id,
    age_group,
    credit_limit,
    max_repayment_delay,
    months_with_delay,
    latest_credit_utilization,
    payment_to_bill_ratio,
    risk_score,
    risk_band,
    risk_reason,

    high_risk_flag,
    serious_delay_flag,
    repeated_delay_flag,
    high_utilization_flag,

    (
        high_risk_flag
        + serious_delay_flag
        + repeated_delay_flag
        + high_utilization_flag
    ) AS triggered_rule_count

FROM review_candidates

WHERE
    high_risk_flag = 1
    OR serious_delay_flag = 1
    OR repeated_delay_flag = 1
    OR high_utilization_flag = 1

ORDER BY
    triggered_rule_count DESC,
    risk_score DESC,
    customer_id

LIMIT 100;


-- ============================================================
-- REPORT 4: MONTHLY BILL AND PAYMENT TRENDS BY SEGMENT
--
-- Compare six-month financial trends across age groups.
-- Monthly bills and payments are joined by customer/month.
-- ============================================================

SELECT
    b.month,
    c.age_group,

    COUNT(DISTINCT c.customer_id) AS customer_count,

    ROUND(
        SUM(b.bill_amount), 2
    ) AS total_monthly_bills,

    ROUND(
        SUM(p.payment_amount), 2
    ) AS total_monthly_payments,

    ROUND(
        AVG(b.bill_amount), 2
    ) AS average_monthly_bill,

    ROUND(
        AVG(p.payment_amount), 2
    ) AS average_monthly_payment,

    ROUND(
        SUM(p.payment_amount) /
        NULLIF(
            SUM(
                CASE
                    WHEN b.bill_amount > 0
                    THEN b.bill_amount
                    ELSE 0
                END
            ), 0
        ),
        4
    ) AS payment_to_positive_bill_ratio

FROM customers c

JOIN bills b
    ON c.customer_id = b.customer_id

JOIN payments p
    ON b.customer_id = p.customer_id
    AND b.month = p.month

GROUP BY
    b.month,
    c.age_group

ORDER BY
    FIELD(
        b.month,
        'APR', 'MAY', 'JUN',
        'JUL', 'AUG', 'SEP'
    ),
    c.age_group;
