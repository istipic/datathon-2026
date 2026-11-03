export interface ErrorStateProps {
  message: string;
  /** When given, a retry button is shown. */
  onRetry?: () => void;
}

/** Error message with an optional retry button. role="alert" announces it immediately. */
export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="dt-state dt-state--error" role="alert">
      <h2 className="dt-state__title">Došlo je do pogreške</h2>
      <p className="dt-state__body">{message}</p>
      {onRetry ? (
        <button type="button" className="dt-button" onClick={onRetry}>
          Pokušaj ponovno
        </button>
      ) : null}
    </div>
  );
}
