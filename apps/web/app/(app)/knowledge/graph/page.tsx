import { GraphExplorer } from "./graph-explorer";

export default async function KnowledgeGraphPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string; id?: string }>;
}) {
  const { type, id } = await searchParams;
  return <GraphExplorer initialEntityType={type ?? null} initialEntityId={id ?? null} />;
}
