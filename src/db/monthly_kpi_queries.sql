
-- ==========================================================
-- BANKING LOAN RISK ANALYSIS
-- STEP 13.2 - MONTHLY BILL AND PAYMENT KPIs
-- ==========================================================


-- KPI 1: MONTHLY BILL TREND
-- Total and average billed amount for each month

SELECT
    b.month,
    COUNT(DISTINCT b.customer_id) AS customer_count,
    ROUND(SUM(b.bill_amount), 2) AS total_bill_amount,
    ROUND(AVG(b.bill_amount), 2) AS average_bill_amount
FROM bills b
GROUP BY b.month
ORDER BY FIELD(
    b.month,
    'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP'
);


-- KPI 2: MONTHLY PAYMENT TREND
-- Total and average payment for each month

SELECT
    p.month,
    COUNT(DISTINCT p.customer_id) AS customer_count,
    ROUND(SUM(p.payment_amount), 2) AS total_payment_amount,
    ROUND(AVG(p.payment_amount), 2) AS average_payment_amount
FROM payments p
GROUP BY p.month
ORDER BY FIELD(
    p.month,
    'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP'
);


-- KPI 3: MONTHLY PAYMENT-TO-BILL RATIO
-- Compare total payments against total billed amounts

SELECT
    b.month,
    ROUND(SUM(b.bill_amount), 2) AS total_bills,
    ROUND(SUM(p.payment_amount), 2) AS total_payments,

    ROUND(
        SUM(p.payment_amount) /
        NULLIF(SUM(b.bill_amount), 0),
        4
    ) AS payment_to_bill_ratio

FROM bills b
JOIN payments p
    ON b.customer_id = p.customer_id
    AND b.month = p.month

GROUP BY b.month

ORDER BY FIELD(
    b.month,
    'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP'
);


-- KPI 4: MONTHLY BILL TREND BY RISK BAND
-- Compare billing patterns across risk categories

SELECT
    b.month,
    r.risk_band,

    COUNT(DISTINCT b.customer_id) AS customer_count,

    ROUND(
        SUM(b.bill_amount), 2
    ) AS total_bill_amount,

    ROUND(
        AVG(b.bill_amount), 2
    ) AS average_bill_amount

FROM bills b

JOIN customer_risk_scores r
    ON b.customer_id = r.customer_id

GROUP BY
    b.month,
    r.risk_band

ORDER BY
    FIELD(
        b.month,
        'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP'
    ),
    FIELD(
        r.risk_band,
        'LOW', 'MEDIUM', 'HIGH', 'UNCLASSIFIED'
    );


-- KPI 5: MONTHLY PAYMENT TREND BY RISK BAND

SELECT
    p.month,
    r.risk_band,

    COUNT(DISTINCT p.customer_id) AS customer_count,

    ROUND(
        SUM(p.payment_amount), 2
    ) AS total_payment_amount,

    ROUND(
        AVG(p.payment_amount), 2
    ) AS average_payment_amount

FROM payments p

JOIN customer_risk_scores r
    ON p.customer_id = r.customer_id

GROUP BY
    p.month,
    r.risk_band

ORDER BY
    FIELD(
        p.month,
        'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP'
    ),
    FIELD(
        r.risk_band,
        'LOW', 'MEDIUM', 'HIGH', 'UNCLASSIFIED'
    );


-- KPI 6: CUSTOMERS WITH INCREASING BILLS
-- Compare April and September bill balances

SELECT
    apr.customer_id,

    apr.bill_amount AS april_bill,
    sep.bill_amount AS september_bill,

    ROUND(
        sep.bill_amount - apr.bill_amount,
        2
    ) AS bill_increase,

    r.risk_band,
    r.risk_score

FROM bills apr

JOIN bills sep
    ON apr.customer_id = sep.customer_id

JOIN customer_risk_scores r
    ON apr.customer_id = r.customer_id

WHERE apr.month = 'APR'
  AND sep.month = 'SEP'
  AND sep.bill_amount > apr.bill_amount

ORDER BY bill_increase DESC
LIMIT 20;


-- KPI 7: CUSTOMERS WITH DECLINING PAYMENTS
-- Compare April and September payments

SELECT
    apr.customer_id,

    apr.payment_amount AS april_payment,
    sep.payment_amount AS september_payment,

    ROUND(
        apr.payment_amount - sep.payment_amount,
        2
    ) AS payment_decrease,

    r.risk_band,
    r.risk_score

FROM payments apr

JOIN payments sep
    ON apr.customer_id = sep.customer_id

JOIN customer_risk_scores r
    ON apr.customer_id = r.customer_id

WHERE apr.month = 'APR'
  AND sep.month = 'SEP'
  AND sep.payment_amount < apr.payment_amount

ORDER BY payment_decrease DESC
LIMIT 20;
