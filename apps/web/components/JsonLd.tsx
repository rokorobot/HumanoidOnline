// A schema.org JSON-LD block. JSON.stringify output is safe, non-user markup.
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger -- JSON.stringify output is safe, non-user markup
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
