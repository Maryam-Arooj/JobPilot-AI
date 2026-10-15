export default function DocumentConfirmation({ facts }: { facts: any[] }) {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">Confirm Extracted Facts</h3>
      {facts?.map((f, i) => (
        <div key={i} className="border p-2 rounded flex justify-between">
          <span>{f.path}: {f.value}</span>
          <span className="text-xs text-muted">{f.confidence}</span>
        </div>
      ))}
    </div>
  );
}
