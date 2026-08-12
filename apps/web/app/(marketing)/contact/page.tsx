import type { Metadata } from "next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SectionHeader } from "@/components/marketing/section-header";

import { ContactForm } from "./contact-form";

export const metadata: Metadata = {
  title: "Contact — Veyntra",
  description: "Request a demo or get in touch with the Veyntra team.",
  alternates: { canonical: "/contact" },
};

export default function ContactPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeader
        eyebrow="Contact"
        title="Request a demo"
        description="Tell us a bit about your organization and we'll get back to you."
      />
      <Card className="mt-10">
        <CardHeader>
          <CardTitle>Your details</CardTitle>
        </CardHeader>
        <CardContent>
          <ContactForm />
        </CardContent>
      </Card>
    </div>
  );
}
