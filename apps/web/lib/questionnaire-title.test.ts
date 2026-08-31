import { describe, expect, it } from "vitest";

import { looksLikeAQuestion } from "./questionnaire-title";

describe("telling a questionnaire's name from one of its questions", () => {
  it.each([
    // The record from the report: a question used as a document title.
    "Do you encrypt customer data at rest?",
    "Do you encrypt customer data at rest",
    "How do you handle incidents",
    "Please describe your access controls",
    "What is your RPO",
    "Is data segregated by tenant?",
  ])("flags %j", (title) => {
    expect(looksLikeAQuestion(title)).toBe(true);
  });

  it.each([
    "Agora Origin Customer Security Questionnaire",
    "Acme Corp vendor security questionnaire",
    "Quarterly Internal GDPR Assessment",
    "Nordwind Robotics DDQ",
    // Not a question, and not anything — an empty box is not a mistake
    // to warn somebody about while they are still typing.
    "",
    "   ",
    // "Doing" starts with the letters of "do" and is not an auxiliary.
    "Doing Business With Acme — security pack",
  ])("leaves %j alone", (title) => {
    expect(looksLikeAQuestion(title)).toBe(false);
  });
});
