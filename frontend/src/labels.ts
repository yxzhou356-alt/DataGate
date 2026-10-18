// Human-readable labels for wire identifiers. Shared by all components.

// The UI offers a fixed catalogue; the backend policy decides what is allowed.
export const PURPOSES = [
  { id: 'feedback_summary', label: 'Summarize customer feedback' },
  { id: 'model_training', label: 'Train a model on this data' },
]

export const DESTINATIONS = [
  { id: 'demo_receiver', label: 'Demo receiver (local)' },
  { id: 'public_chatbot', label: 'Public chatbot' },
]

export function purposeLabel(id: string): string {
  return PURPOSES.find((p) => p.id === id)?.label ?? id
}

export function destinationLabel(id: string): string {
  return DESTINATIONS.find((d) => d.id === id)?.label ?? id
}

export function redactionLabel(type: string): string {
  return ({ EMAIL: 'email addresses', PHONE: 'phone numbers', PERSON: 'person names' } as Record<string, string>)[type] ?? type
}

/** Short word shown inside a redaction marker. */
export function redactionShortLabel(type: string): string {
  return ({ EMAIL: 'email', PHONE: 'phone', PERSON: 'person' } as Record<string, string>)[type] ?? type.toLowerCase()
}

export function redactionCountLabel(type: string, count: number): string {
  const singular = ({ EMAIL: 'email address', PHONE: 'phone number', PERSON: 'person name' } as Record<string, string>)[type] ?? type
  return `${count} ${count === 1 ? singular : redactionLabel(type)}`
}

export function sourceFieldLabel(field: string): string {
  return ({
    ticket_id: 'ticket IDs', customer_name: 'customer names', email: 'email addresses',
    phone: 'phone numbers', plan_tier: 'subscription plans', account_value: 'account values',
    product_area: 'product categories',
  } as Record<string, string>)[field] ?? field
}

export function outboundFieldLabel(field: string): string {
  return ({ message: 'Feedback message only' } as Record<string, string>)[field] ?? field
}

export function receiverLabel(mode: string): string {
  return ({ local_demo: 'Local demo receiver' } as Record<string, string>)[mode] ?? mode
}

export function decisionLabel(d: string): string {
  return ({ allow: 'Allowed', redact: 'Allowed with redaction', block: 'Blocked' } as Record<string, string>)[d] ?? d
}
