import { render, screen } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { expect, it } from "vitest";
import "@/i18n";
import type { ProductInput } from "@/hooks/useProduct";
import { ProductClassification } from "./index";

function Fields({ clientId }: { clientId?: string }) {
  const { register } = useForm<ProductInput>({ defaultValues: { kind: "software", sellable: false } });
  return <ProductClassification register={register} clientId={clientId} prefix="test" />;
}

it("offers product types and disables sale for a client", () => {
  const { rerender } = render(<Fields />);
  expect(screen.getByRole("combobox")).toHaveValue("software");
  expect(screen.getAllByRole("option")).toHaveLength(4);
  expect(screen.getByRole("checkbox")).toBeEnabled();
  rerender(<Fields clientId="client" />);
  expect(screen.getByRole("checkbox")).toBeDisabled();
  expect(screen.getByText(/client products cannot|produtos de cliente|productos de clientes/i)).toBeInTheDocument();
});
