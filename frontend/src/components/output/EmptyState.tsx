interface EmptyStateProps {
  icon: string;
  children: React.ReactNode;
}

export function EmptyState({ icon, children }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="icon" aria-hidden="true">
        {icon}
      </div>
      {children}
    </div>
  );
}
