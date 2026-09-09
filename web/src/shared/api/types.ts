// Types de domaine côté client. L'API documente peu ses réponses ; ces types sont
// volontairement permissifs et alignés sur les `to_dict()` du backend.

export type Wallet = {
  id: string;
  currency: string;
  status: string;
  available_minor: number;
  reserved_minor: number;
  vaulted_minor: number;
  saved_minor: number;
  balance_minor: number;
  created_at: string;
};

export type StatementLine = {
  id: string;
  reference: string;
  kind: string;
  direction: 'in' | 'out';
  amount_minor: number;
  fee_minor: number;
  currency: string;
  counterparty_masked: string | null;
  note: string | null;
  occurred_at: string;
};

export type StatementPage = { lines: StatementLine[]; next_cursor: string | null };

export type TransferReceipt = {
  transfer_id?: string;
  reference?: string;
  amount_minor?: number;
  fee_minor?: number;
  total_minor?: number;
  currency?: string;
  recipient_masked?: string;
  occurred_at?: string;
  balance_after_minor?: number;
  [k: string]: unknown;
};

export type KycStatus = {
  tier: number;
  status?: string;
  pending_case_id?: string | null;
  limits?: Record<string, unknown>;
  [k: string]: unknown;
};

export type PaymentRequest = {
  request_id: string;
  direction: 'incoming' | 'outgoing';
  status: string;
  amount_minor: number;
  currency: string;
  counterparty_masked?: string;
  note?: string | null;
  created_at: string;
  [k: string]: unknown;
};

export type VaultPocket = {
  pocket_id: string;
  name: string;
  balance_minor: number;
  goal_minor: number | null;
  locked_until: string | null;
  currency: string;
  [k: string]: unknown;
};

export type Vault = { currency: string; total_minor: number; pockets: VaultPocket[] };

export type SavingsPlan = {
  plan_id: string;
  name: string;
  balance_minor: number;
  target_minor: number | null;
  accrued_interest_minor?: number;
  status: string;
  currency: string;
  frequency?: string;
  [k: string]: unknown;
};

export type Card = {
  card_id: string;
  network: string;
  last4: string;
  status: string;
  expiry_month: number;
  expiry_year: number;
  daily_limit_minor: number;
  monthly_limit_minor: number;
  channels: string[];
  currency: string;
  [k: string]: unknown;
};

export type PhoneNumber = {
  phone_number: string;
  masked?: string;
  is_primary: boolean;
  verified: boolean;
  [k: string]: unknown;
};

export type Notification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
  [k: string]: unknown;
};

export type CashOrder = {
  order_id: string;
  code?: string;
  amount_minor: number;
  fee_minor: number;
  currency: string;
  status: string;
  expires_at?: string;
  [k: string]: unknown;
};

export type Country = {
  code: string;
  name: string;
  currency: string;
  dialing_code: string;
  operators?: { code: string; name: string }[];
};
