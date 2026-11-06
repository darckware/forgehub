import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { MaintenanceProposalsCard } from "./MaintenanceProposalsCard";
vi.mock("@/lib/api", () => ({apiClient: {get: vi.fn(), post: vi.fn()}}));
const proposal = {id:"p1",message_number:42,status:"proposed",reason:"Install tool",content:"sudo apt install example",shell:"sh",risk:"change",timeout_seconds:30,requires_elevation:true,content_hash:"a".repeat(64),expected_effect:"Available",rollback:"Remove package",machines:[{id:"m1",name:"linux-target.test"}],parameters:[]};
function wrap() {return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MaintenanceProposalsCard /></QueryClientProvider>);}
describe("maintenance proposals", () => {
  it("shows the complete script, elevation and hash and sends the displayed hash", async () => {
    await i18n.changeLanguage("pt-BR");vi.mocked(apiClient.get).mockResolvedValue([proposal]);vi.mocked(apiClient.post).mockResolvedValue({});
    wrap();fireEvent.click(await screen.findByRole("button",{name:"Ver proposta"}));
    expect(screen.getByText(proposal.content)).toBeInTheDocument();expect(screen.getByText(proposal.content_hash)).toBeInTheDocument();expect(screen.getByRole("note")).toHaveTextContent("elevação");
    fireEvent.click(screen.getByRole("button",{name:"Aprovar"}));
    await vi.waitFor(()=>expect(apiClient.post).toHaveBeenCalledWith("/api/v1/maintenance-proposals/p1/decision",{decision:"approved",content_hash:proposal.content_hash,reason:null}));
  });
  it("requires a rejection reason and preserves the script on failure", async () => {
    await i18n.changeLanguage("pt-BR");vi.mocked(apiClient.get).mockResolvedValue([proposal]);vi.mocked(apiClient.post).mockRejectedValue(new Error("Hash changed: review again"));
    wrap();fireEvent.click(await screen.findByRole("button",{name:"Ver proposta"}));fireEvent.click(screen.getByRole("button",{name:"Recusar"}));
    expect(screen.getByRole("button",{name:"Recusar"})).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Motivo da recusa"),{target:{value:"Wrong target"}});fireEvent.click(screen.getByRole("button",{name:"Recusar"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Hash changed");expect(screen.getByText(proposal.content)).toBeInTheDocument();
  });
});
