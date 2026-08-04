"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ApiError, apiFetch } from "@/lib/api";
import {
  BUSINESS_RULE_ACTION_TYPES,
  BUSINESS_RULE_OPERATORS,
  BUSINESS_RULE_TRIGGER_TYPES,
  SYSTEM_ROLES,
  type BusinessRule,
} from "@/lib/types";

function CreateRuleForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<string>(BUSINESS_RULE_TRIGGER_TYPES[0]);
  const [conditionField, setConditionField] = useState("");
  const [conditionOperator, setConditionOperator] = useState<string>(BUSINESS_RULE_OPERATORS[0]);
  const [conditionValue, setConditionValue] = useState("");
  const [actionType, setActionType] = useState<string>(BUSINESS_RULE_ACTION_TYPES[0]);
  const [actionRoleKey, setActionRoleKey] = useState<string>(SYSTEM_ROLES[0].key);

  const create = useMutation({
    mutationFn: () =>
      apiFetch<BusinessRule>("/api/v1/business-rules", {
        method: "POST",
        body: {
          name,
          trigger_type: triggerType,
          condition_field: conditionField,
          condition_operator: conditionOperator,
          condition_value: conditionValue,
          action_type: actionType,
          action_role_key: actionRoleKey,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-rules"] });
      setName("");
      setConditionField("");
      setConditionValue("");
    },
  });

  return (
    <Card className="mb-6 max-w-3xl">
      <CardContent className="flex flex-col gap-3 pt-6">
        <h2 className="text-sm font-semibold text-neutral-900">Add a business rule</h2>
        <p className="text-xs text-neutral-500">
          A structured condition against a real event — never text embedded in an AI prompt.
        </p>
        <Input placeholder="Rule name" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="flex flex-wrap gap-2">
          <Select value={triggerType} onChange={(e) => setTriggerType(e.target.value)} className="w-52">
            {BUSINESS_RULE_TRIGGER_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          <Input
            placeholder="field (e.g. severity)"
            value={conditionField}
            onChange={(e) => setConditionField(e.target.value)}
            className="w-40"
          />
          <Select
            value={conditionOperator}
            onChange={(e) => setConditionOperator(e.target.value)}
            className="w-20"
          >
            {BUSINESS_RULE_OPERATORS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </Select>
          <Input
            placeholder="value (e.g. critical)"
            value={conditionValue}
            onChange={(e) => setConditionValue(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Select value={actionType} onChange={(e) => setActionType(e.target.value)} className="w-44">
            {BUSINESS_RULE_ACTION_TYPES.map((a) => (
              <option key={a} value={a}>
                {a.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          <Select value={actionRoleKey} onChange={(e) => setActionRoleKey(e.target.value)} className="w-56">
            {SYSTEM_ROLES.map((role) => (
              <option key={role.key} value={role.key}>
                {role.name}
              </option>
            ))}
          </Select>
        </div>
        {create.isError && (
          <p className="text-sm text-red-600">
            {create.error instanceof ApiError ? create.error.message : "Could not save rule."}
          </p>
        )}
        <div>
          <Button
            size="sm"
            disabled={!name.trim() || !conditionField.trim() || !conditionValue.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Save rule
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function RuleRow({ rule }: { rule: BusinessRule }) {
  const queryClient = useQueryClient();

  const toggle = useMutation({
    mutationFn: () =>
      apiFetch<BusinessRule>(`/api/v1/business-rules/${rule.id}`, {
        method: "PATCH",
        body: { is_active: !rule.is_active },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["business-rules"] }),
  });

  const remove = useMutation({
    mutationFn: () => apiFetch(`/api/v1/business-rules/${rule.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["business-rules"] }),
  });

  return (
    <Card>
      <CardContent className="flex items-center justify-between pt-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-neutral-900">{rule.name}</span>
            <Badge variant={rule.is_active ? "default" : "outline"}>
              {rule.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-neutral-500">
            When <span className="capitalize">{rule.trigger_type.replace(/_/g, " ")}</span>: {rule.condition_field}{" "}
            {rule.condition_operator} {rule.condition_value} → {rule.action_type.replace(/_/g, " ")} (
            {rule.action_role_key})
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
            {rule.is_active ? "Deactivate" : "Activate"}
          </Button>
          <Button size="sm" variant="outline" disabled={remove.isPending} onClick={() => remove.mutate()}>
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function BusinessRulesPage() {
  const { data: rules, isLoading } = useQuery<BusinessRule[]>({
    queryKey: ["business-rules"],
    queryFn: () => apiFetch<BusinessRule[]>("/api/v1/business-rules"),
  });

  return (
    <div>
      <PageHeader
        title="Business Rules"
        description="spec §90 — condition -> required approval or notification, evaluated on the same
          real events Automation workflows already trigger on. Separate from AI prompts, per spec."
      />

      <CreateRuleForm />

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {rules && rules.length === 0 && (
        <p className="text-sm text-neutral-500">No business rules configured yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {rules?.map((rule) => (
          <RuleRow key={rule.id} rule={rule} />
        ))}
      </div>
    </div>
  );
}
