import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type EntityTab = {
  value: string;
  label: string;
  content: React.ReactNode;
  badge?: React.ReactNode;
};

/** Convenience wrapper over ui/tabs for the common detail-page shape —
 * pass a flat list of {value, label, content} instead of hand-assembling
 * TabsList/TabsTrigger/TabsContent on every entity page. */
export function EntityTabs({
  tabs,
  defaultValue,
}: {
  tabs: EntityTab[];
  defaultValue?: string;
}) {
  return (
    <Tabs defaultValue={defaultValue ?? tabs[0]?.value}>
      <TabsList>
        {tabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value} className="flex items-center gap-1.5">
            {tab.label}
            {tab.badge}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value}>
          {tab.content}
        </TabsContent>
      ))}
    </Tabs>
  );
}
