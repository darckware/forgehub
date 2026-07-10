# Screen: Products

## Route & Purpose

| Route | Component | Purpose |
|---|---|---|
| `/product` | `ProductPage` (`frontend/src/pages/product/index.tsx`) | List all products, create a new product, delete a product. |
| `/product/:id` | `ProductDetail` (`frontend/src/pages/product/ProductDetail.tsx`) | Show one product's detail (name, description, status badge) plus its `ProductVersion[]`, and create a new version. |

Both routes are registered in `frontend/src/App.tsx:37-38`. The sidebar exposes a single "Products" nav entry pointing at `/product` (`frontend/src/components/layout/Sidebar.tsx:58`); there is no separate nav entry for the detail view (reached only via the row link from the list).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/product/index.tsx` | List view. Renders the page header, an inline "New Product" creation form (toggled by a button, not a modal/route), and a table of products with a row link to the detail page and a delete action per row. |
| `frontend/src/pages/product/ProductDetail.tsx` | Detail view. Renders a back link, product header (name/description/status badge), an inline "New Version" creation form, and a table of the product's versions. |
| `frontend/src/hooks/useProduct.ts` | TanStack Query hooks + Zod schemas for `Product`/`ProductVersion`, and the create/delete mutations for `Product`. Also defines `useUpdateProduct` (unused by any current screen). |
| `frontend/src/components/ui/{card,input,label,textarea,select,badge,table,button}.tsx` | shadcn/ui primitives used to build both forms and tables. |
| `frontend/src/lib/api.ts` | Shared `apiClient` fetch wrapper used by all hooks/inline mutations on this screen. |

Note: the version-creation mutation (`useCreateProductVersion`) is defined locally inside `ProductDetail.tsx:54-67`, not in `useProduct.ts` — it is the one hook for this screen family that does not live in the shared hooks file.

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Product list (table rows: name, description, status, version count) | `useProducts()` (`useProduct.ts:50-55`) | `/api/v1/products` | GET |
| Single product + nested versions (detail header + versions table) | `useProduct(id)` (`useProduct.ts:57-63`) | `/api/v1/products/{id}` | GET |
| Create product (+ auto-created initial version server-side) | `useCreateProduct()` (`useProduct.ts:65-73`) | `/api/v1/products` | POST |
| Delete product | `useDeleteProduct()` (`useProduct.ts:87-95`) | `/api/v1/products/{id}` | DELETE |
| Create product version | `useCreateProductVersion(productId)` (`ProductDetail.tsx:54-67`, local to this file) | `/api/v1/product-versions` (as called) | POST |

**`useUpdateProduct(id)`** (`useProduct.ts:75-85`) exists and would call `PATCH /api/v1/products/{id}`, but is not used by either `ProductPage` or `ProductDetail` — there is no edit-product UI on this screen family. It is also a method mismatch: the backend only exposes `PUT /api/v1/products/{product_id}` (`backend/app/api/routes/product.py:126`), not `PATCH` — so even if wired up, this hook would fail against the real backend.

## Actions Available

**List view (`/product`):**
- **New Product** button — toggles an inline creation `Card` form (name, description, status select). On submit, calls `useCreateProduct`, resets the form, and hides it. On failure, shows an inline "Failed to create product. Please try again." message but the form/card stays open.
- **Row click on product name** — navigates to `/product/:id`.
- **Delete icon (trash)** per row — calls `deleteProduct.mutate(product.id)` immediately, no confirmation dialog. Disabled while a delete is pending.
- **Retry** button (only shown on error state) — calls `refetch()`.

**Detail view (`/product/:id`):**
- **Back to products** link — navigates to `/product`.
- **New Version** button — toggles an inline creation `Card` form (version string, status select, release date, notes). On submit, calls the local `useCreateProductVersion` mutation, resets the form, and hides it. On failure, shows an inline error message.
- **Retry** button (only shown on error state) — calls `refetch()`.
- No edit or delete action exists for either the product or its versions on this screen (delete-version and update-version both exist in the backend but are not surfaced here).

## States

| State | List view | Detail view |
|---|---|---|
| Loading | Centered spinner + "Loading products..." inside the table card (`index.tsx:145-150`) | Full-page centered spinner + "Loading product..." (`ProductDetail.tsx:91-98`) |
| Error | Inline destructive-colored message (`error.message` or fallback) + Retry button, scoped to the table card (`index.tsx:152-161`) | Whole-page error card with the same message/Retry pattern, plus the back link (`ProductDetail.tsx:100-119`) |
| Empty | `PackageSearch` icon + "No products yet" + "Create your first product to get started." (`index.tsx:163-169`) | `Tag` icon + "No versions yet" + "Create the first version for this product." (`ProductDetail.tsx:218-223`) |
| Mutation error (create) | Inline destructive text inside the create-product form card, form stays open (`index.tsx:117-121`) | Inline destructive text inside the create-version form card, form stays open (`ProductDetail.tsx:190-194`) |
| Mutation error (delete) | **Not handled** — `deleteProduct.isError` is never read/rendered; a failed delete fails silently from the user's perspective | n/a (no delete action on this view) |

## Business Rules Surfaced Here

Per `docs/BUSINESS_RULES.md` §1 (Product Rules):

- **Rule 1 (unique product name)** — surfaced indirectly: the create-product form description text says "Name must be unique" (`index.tsx:85`), but the screen does nothing client-side to pre-validate or distinctly surface the resulting 409; a failed create just shows the generic "Failed to create product" message, not the specific uniqueness reason.
- **Rule 3 (every product must have ≥1 version)** — surfaced indirectly only: the backend auto-creates an initial version on `create_product` (`backend/app/api/routes/product.py:71-104`), and the detail screen's version count column / versions table reflects that. The screen itself has no UI text explaining this invariant, and there is no way to delete a version from this screen at all (so the "cannot delete the last version" 422 path is unreachable from this screen — see Notes).
- **Rule 4 (published versions cannot be mutated directly)** — **not surfaced**. There is no edit-version UI on this screen, so the rule is never exercised or displayed here (it could only be hit via direct API calls or a different screen).
- **Rule 5 (fixes for published versions need patch/hotfix flow)** — not applicable to this screen; belongs to Backlog/Planning screens.

## Dependencies

- **Product domain** (`backend/app/db/models/product.py`, `backend/app/api/routes/product.py`): `Product`, `ProductVersion` are read/written directly by this screen. `ProductModule` and `Release` are part of the same domain/router but are not touched by this screen (see Notes).
- No other domain is referenced directly from this screen (no project, pipeline, backlog, task, artifact, or governance data is shown here). `ProductVersion.id` is, however, a required FK consumed downstream by the Project domain (`projects.product_version_id`) — not visible on this screen but worth knowing when reasoning about why a version can't be freely deleted.

## Notes / Improvement Opportunities

- **Release has no frontend page or hook — confirmed gap.** `backend/app/api/routes/product.py:347-412` implements full CRUD for `Release` (`POST/GET/PUT/DELETE /api/v1/products/releases...`), and the model exists in `backend/app/db/models/product.py:104-122`, but a repo-wide search found zero frontend references to a release page or `useRelease`-style hook — `Release` is unreachable from the UI entirely. This matches the gap already flagged in `docs/DATA_MODEL.md` §3.1.
- **`ProductModule` also has no frontend surface.** The backend exposes full CRUD for modules nested under a product (`/api/v1/products/{id}/modules`, `backend/app/api/routes/product.py:160-223`), and `Product.modules` is even eagerly loaded by `GET /api/v1/products/{id}` (`selectinload(Product.modules)`, `product.py:118`), but neither `ProductPage` nor `ProductDetail` renders or fetches modules. This is the same class of gap as Release and is not yet documented elsewhere — flagging it here.
- **Broken endpoint: version creation calls a path the backend does not expose.** `ProductDetail.tsx:58` calls `apiClient.post<ProductVersion>("/api/v1/product-versions", { ...payload, product_id: productId })`. The backend has no top-level `/api/v1/product-versions` collection route — version creation is only mounted at `POST /api/v1/products/{product_id}/versions` (`backend/app/api/routes/product.py:231-261`), which doesn't take `product_id` in the body at all (it's a path param). As written, clicking "Save" on the New Version form will hit a 404 against the real backend. This looks like a leftover from an earlier, flatter routing convention (the comment block in `frontend/src/lib/api.ts:5-9` still documents `/api/v1/product-versions` as the expected convention, suggesting the routes were re-nested under `/products/{id}/versions` on the backend without the frontend being updated).
- **Field name/shape mismatches between the version form and the backend model.** The create-version form (`ProductDetail.tsx:42-50`) collects and submits `release_date` and `notes`, and its Zod schema's `status` enum includes `"archived"`. The backend `ProductVersion` model/schema has neither a `release_date` column nor a `notes` field — only `release_notes` (`backend/app/db/models/product.py:96`, `backend/app/api/schemas/product.py:42-45`) — and its status `CheckConstraint`/`PRODUCT_VERSION_STATUSES` allow `"deprecated"`, not `"archived"` (`backend/app/db/models/product.py:42,82`). Even if the path mismatch above were fixed, this payload would still be rejected or silently drop `release_date`/`notes` server-side.
- **`Product.status` does not exist on the backend model at all.** The `Product` SQLAlchemy model (`backend/app/db/models/product.py:48-60`) only has `id`, `name`, `description` — no `status` column. Yet `frontend/src/hooks/useProduct.ts:27-35` declares `productSchema.status` (`active|inactive|archived`, defaulted client-side), the list view renders a status `Badge` per product (`index.tsx:197-204`), the create-product form includes a status `Select` (`index.tsx:108-115`), and the detail view also renders a product-level status badge (`ProductDetail.tsx:135-137`). None of this status data exists in the database or the API response — the badge will always show whatever Zod's `.default("active")` fills in, since the backend never returns a `status` field for `ProductOut`/`ProductWithVersionsOut` (`backend/app/api/schemas/product.py:94-106`). This is a significant, currently-invisible frontend/backend contract drift, distinct from (and more severe than) the version-creation routing bug above.
- **Delete has no confirmation step.** The product list's delete (trash) icon fires `deleteProduct.mutate(product.id)` directly on click (`index.tsx:212`) with no confirmation dialog — a misclick permanently deletes a product (and cascades to its versions/modules via the ORM relationship `cascade="all, delete-orphan"`, `backend/app/db/models/product.py:55-60`).
- **Delete-mutation errors are swallowed.** `deleteProduct.isError`/`deleteProduct.error` are never read in `index.tsx`, so if the backend rejects a delete (e.g. some future FK constraint, or a network failure) the row simply stays in place with no feedback to the user about why.
- **No edit UI for Product or ProductVersion on this screen.** `useUpdateProduct` is defined (`useProduct.ts:75-85`) but never called from any component — dead code from the screen's perspective — and there is no version-update or version-delete UI at all, even though both exist in the backend (`update_product_version`/`delete_product_version`, `backend/app/api/routes/product.py:282-339`). This means Business Rule 4 (published versions immutable) can never be exercised through this screen as it stands today.
