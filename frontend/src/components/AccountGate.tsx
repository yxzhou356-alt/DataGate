interface Props {
  busy: boolean
  onSelect: (accountId: string) => void
  error?: string | null
}

const ACCOUNTS = [
  { id: 'analyst_a', name: 'MapleCo analyst', note: 'Can use MapleCo feedback' },
  { id: 'analyst_b', name: 'RiverCo analyst', note: 'Can use RiverCo feedback' },
]

export function AccountGate({ busy, onSelect, error }: Props) {
  return (
    <main className="gate">
      <div className="gate-inner">
        <h1 className="wordmark">DataGate</h1>
        <p className="gate-lede">
          Permission, review, and evidence before customer data reaches AI.
        </p>
        <p className="gate-caution">
          Demo sign-in. Pick a seeded analyst to get a session token from the backend.
          This is a local simulation, not real authentication.
        </p>
        {error && <p className="notice" role="alert">{error}</p>}
        <div className="gate-accounts">
          {ACCOUNTS.map((a) => (
            <button key={a.id} className="account-card" disabled={busy} onClick={() => onSelect(a.id)}>
              <span className="account-name">{a.name}</span>
              <span className="account-note">{a.note}</span>
              <code className="account-id">{a.id}</code>
            </button>
          ))}
        </div>
      </div>
    </main>
  )
}
