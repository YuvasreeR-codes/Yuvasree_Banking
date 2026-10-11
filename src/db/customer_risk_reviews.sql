CREATE TABLE customer_risk_reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    review_status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    priority VARCHAR(10) NOT NULL DEFAULT 'Medium',
    review_notes TEXT,
    review_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_review_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id),

    CONSTRAINT chk_review_status
        CHECK (review_status IN (
            'Pending', 'In Progress', 'Completed'
        )),

    CONSTRAINT chk_review_priority
        CHECK (priority IN (
            'Low', 'Medium', 'High'
        ))
);