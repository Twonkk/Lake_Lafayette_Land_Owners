SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS owners (
        owner_code TEXT PRIMARY KEY,
        last_name TEXT,
        first_name TEXT,
        secondary_owner_flag TEXT,
        note_number INTEGER,
        address TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        phone TEXT,
        status TEXT,
        resident_flag TEXT,
        plat TEXT,
        current_flag TEXT,
        sale_date TEXT,
        hold_mail_flag TEXT,
        ineligible_flag TEXT,
        collection_flag TEXT,
        collection_date TEXT,
        lien_flag TEXT,
        number_lots INTEGER DEFAULT 0,
        primary_lot_number TEXT,
        total_owed NUMERIC DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lots (
        lot_number TEXT PRIMARY KEY,
        owner_code TEXT,
        current_assessment NUMERIC DEFAULT 0,
        delinquent_assessment NUMERIC DEFAULT 0,
        delinquent_interest NUMERIC DEFAULT 0,
        current_interest NUMERIC DEFAULT 0,
        total_due NUMERIC DEFAULT 0,
        payment_amount NUMERIC DEFAULT 0,
        previous_review_date TEXT,
        last_review_date TEXT,
        pay_date TEXT,
        paid_through TEXT,
        payment_form TEXT,
        lien_flag TEXT,
        lakefront_flag TEXT,
        dock_flag TEXT,
        development_status TEXT,
        collection_flag TEXT,
        freeze_flag TEXT,
        appraised_value NUMERIC DEFAULT 0,
        assessed_value NUMERIC DEFAULT 0,
        note_number INTEGER,
        lien_amount NUMERIC DEFAULT 0,
        lien_on_date TEXT,
        lien_off_date TEXT,
        lien_book_page TEXT,
        lien_book INTEGER,
        lien_page INTEGER,
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS owner_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_code TEXT NOT NULL,
        payment_amount NUMERIC NOT NULL,
        total_owed NUMERIC,
        payment_date TEXT,
        payment_form TEXT,
        check_number TEXT,
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lot_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lot_number TEXT NOT NULL,
        owner_code TEXT,
        payment_amount NUMERIC NOT NULL,
        payment_date TEXT,
        payment_form TEXT,
        check_number TEXT,
        number_lots INTEGER,
        delinquent_assessment_1 NUMERIC,
        delinquent_interest_1 NUMERIC,
        current_assessment_1 NUMERIC,
        current_interest_1 NUMERIC,
        delinquent_assessment_2 NUMERIC,
        delinquent_interest_2 NUMERIC,
        current_assessment_2 NUMERIC,
        current_interest_2 NUMERIC,
        total_posted NUMERIC,
        posted_flag TEXT,
        payment_method TEXT,
        FOREIGN KEY (lot_number) REFERENCES lots(lot_number),
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_code TEXT,
        note_number INTEGER,
        note_text TEXT NOT NULL,
        review_date TEXT,
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_accounts (
        account_code TEXT PRIMARY KEY,
        account_name TEXT NOT NULL,
        category TEXT,
        fiscal_year TEXT,
        monthly_budget NUMERIC,
        yearly_budget NUMERIC,
        file_status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_number TEXT,
        fiscal_year TEXT,
        month_number INTEGER,
        entry_date TEXT,
        transaction_date TEXT,
        month_code TEXT,
        account_code TEXT,
        amount NUMERIC NOT NULL,
        payee TEXT,
        memo TEXT,
        reference_number TEXT,
        check_number TEXT,
        paper_check_flag TEXT,
        payment_method TEXT,
        pc_transaction_number TEXT,
        disposition TEXT,
        transaction_type TEXT,
        status TEXT,
        FOREIGN KEY (account_code) REFERENCES financial_accounts(account_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_monthly (
        account_code TEXT NOT NULL,
        fiscal_year TEXT DEFAULT '',
        fiscal_month INTEGER NOT NULL,
        calendar_month INTEGER,
        previous_balance NUMERIC DEFAULT 0,
        month_expense NUMERIC DEFAULT 0,
        month_deposit NUMERIC DEFAULT 0,
        year_to_date NUMERIC DEFAULT 0,
        budget_to_date NUMERIC DEFAULT 0,
        monthly_budget NUMERIC DEFAULT 0,
        yearly_budget NUMERIC DEFAULT 0,
        file_status TEXT,
        PRIMARY KEY (account_code, fiscal_year, fiscal_month),
        FOREIGN KEY (account_code) REFERENCES financial_accounts(account_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        source_dir TEXT NOT NULL,
        status TEXT NOT NULL,
        owners_imported INTEGER DEFAULT 0,
        lots_imported INTEGER DEFAULT 0,
        owner_payments_imported INTEGER DEFAULT 0,
        lot_payments_imported INTEGER DEFAULT 0,
        notes_imported INTEGER DEFAULT 0,
        finished_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payment_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        owner_code TEXT NOT NULL,
        lot_number TEXT NOT NULL,
        payment_amount NUMERIC NOT NULL,
        payment_date TEXT NOT NULL,
        payment_form TEXT NOT NULL,
        check_number TEXT,
        note_text TEXT,
        backup_path TEXT,
        previous_total_due NUMERIC NOT NULL,
        new_total_due NUMERIC NOT NULL,
        previous_owner_total NUMERIC NOT NULL,
        new_owner_total NUMERIC NOT NULL,
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code),
        FOREIGN KEY (lot_number) REFERENCES lots(lot_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assessment_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        assessment_amount NUMERIC NOT NULL,
        assessment_date TEXT NOT NULL,
        backup_path TEXT NOT NULL,
        lots_updated INTEGER NOT NULL,
        owners_updated INTEGER NOT NULL,
        excluded_lots INTEGER NOT NULL,
        freeze_lots INTEGER NOT NULL,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS property_sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        sale_date TEXT NOT NULL,
        lot_number TEXT NOT NULL,
        seller_owner_code TEXT NOT NULL,
        buyer_owner_code TEXT NOT NULL,
        new_buyer_flag TEXT,
        backup_path TEXT,
        reversed_at TEXT,
        reversal_backup_path TEXT,
        FOREIGN KEY (lot_number) REFERENCES lots(lot_number),
        FOREIGN KEY (seller_owner_code) REFERENCES owners(owner_code),
        FOREIGN KEY (buyer_owner_code) REFERENCES owners(owner_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS boat_sticker_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        owner_code TEXT NOT NULL,
        lot_number TEXT,
        sticker_year TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        amount NUMERIC NOT NULL,
        notes TEXT,
        backup_path TEXT,
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code),
        FOREIGN KEY (lot_number) REFERENCES lots(lot_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS id_card_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        owner_code TEXT NOT NULL,
        lot_number TEXT,
        issue_date TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        notes TEXT,
        backup_path TEXT,
        FOREIGN KEY (owner_code) REFERENCES owners(owner_code),
        FOREIGN KEY (lot_number) REFERENCES lots(lot_number)
    )
    """,
]
