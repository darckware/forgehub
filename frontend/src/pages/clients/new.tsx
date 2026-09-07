import { FormEvent, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateClient, type ClientCreate } from "@/hooks/useClients";

const INITIAL_FORM = {
  name: "",
  contact_name: "",
  contact_phone: "",
  contact_email: "",
  support_plan: "",
  notes: "",
};

export default function NewClientPage() {
  const { t } = useTranslation("clients");
  const navigate = useNavigate();
  const createClient = useCreateClient();
  const [form, setForm] = useState(INITIAL_FORM);
  const [nameError, setNameError] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = `${t("create.title")} — ForgeHub`;
  }, [t]);

  function setField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    if (field === "name" && value.trim()) setNameError("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) {
      setNameError(t("create.nameRequired"));
      nameRef.current?.focus();
      return;
    }

    const payload: ClientCreate = {
      name,
      contact_name: form.contact_name.trim() || null,
      contact_phone: form.contact_phone.trim() || null,
      contact_email: form.contact_email.trim() || null,
      support_plan: form.support_plan || null,
      notes: form.notes.trim() || null,
    };
    createClient.mutate(payload, { onSuccess: () => navigate("/clients") });
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <Breadcrumb items={[{ label: t("list.title"), href: "/clients" }, { label: t("create.title") }]} className="mb-5" />
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">{t("create.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("create.description")}</p>
      </header>

      <section className="w-full max-w-3xl overflow-hidden rounded-lg border border-border bg-card" aria-labelledby="client-details-heading">
        <div className="border-b border-border px-6 py-4">
          <h2 id="client-details-heading" className="text-sm font-semibold">{t("create.details")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("create.requiredHint")}</p>
        </div>
        <form className="space-y-5 p-6" noValidate onSubmit={handleSubmit}>
          {createClient.isError && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {t("create.submitError")}
            </p>
          )}

          <div className="space-y-2">
            <Label htmlFor="client-name">{t("create.fields.name")} *</Label>
            <Input
              ref={nameRef}
              id="client-name"
              name="name"
              autoComplete="organization"
              value={form.name}
              onChange={(event) => setField("name", event.target.value)}
              aria-invalid={Boolean(nameError)}
              aria-describedby="client-name-help client-name-error"
              disabled={createClient.isPending}
            />
            <p id="client-name-help" className="text-xs text-muted-foreground">{t("create.nameHelp")}</p>
            <p id="client-name-error" className="min-h-4 text-xs text-destructive" aria-live="polite">{nameError}</p>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="contact-name">{t("create.fields.contactName")}</Label>
              <Input id="contact-name" autoComplete="name" value={form.contact_name} onChange={(event) => setField("contact_name", event.target.value)} disabled={createClient.isPending} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-phone">{t("create.fields.phone")}</Label>
              <Input id="contact-phone" type="tel" autoComplete="tel" value={form.contact_phone} onChange={(event) => setField("contact_phone", event.target.value)} disabled={createClient.isPending} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="contact-email">{t("create.fields.email")}</Label>
            <Input id="contact-email" type="email" autoComplete="email" value={form.contact_email} onChange={(event) => setField("contact_email", event.target.value)} disabled={createClient.isPending} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="support-plan">{t("create.fields.supportPlan")}</Label>
            <Select id="support-plan" value={form.support_plan} onChange={(event) => setField("support_plan", event.target.value)} disabled={createClient.isPending}>
              <option value="">{t("supportPlans.none")}</option>
              <option value="4h">{t("supportPlans.4h")}</option>
              <option value="8h">{t("supportPlans.8h")}</option>
              <option value="12h">{t("supportPlans.12h")}</option>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="client-notes">{t("create.fields.notes")}</Label>
            <Textarea id="client-notes" rows={4} className="resize-none" value={form.notes} onChange={(event) => setField("notes", event.target.value)} disabled={createClient.isPending} />
          </div>

          <div className="flex justify-end gap-3 border-t border-border pt-5">
            <Link
              to="/clients"
              aria-disabled={createClient.isPending}
              className={buttonVariants({ variant: "outline", className: createClient.isPending ? "pointer-events-none opacity-50" : undefined })}
            >
              {t("common.cancel")}
            </Link>
            <Button type="submit" disabled={createClient.isPending} aria-busy={createClient.isPending} className="min-w-32">
              {createClient.isPending && <Loader2 className="mr-1.5 h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />}
              {t("create.submit")}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
