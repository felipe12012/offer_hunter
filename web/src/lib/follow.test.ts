import { describe, expect, it } from "vitest";

import { followLink } from "./follow";

describe("followLink", () => {
  it("arma el enlace al bot con la tienda y el sku", () => {
    expect(followLink("falabella", "12345", "CazaOfertasBot")).toBe("https://t.me/CazaOfertasBot?start=seguir_falabella_12345");
    expect(followLink("hites", "10052004071002", "@MiBot_bot")).toBe("https://t.me/MiBot_bot?start=seguir_hites_10052004071002");
  });

  it("sin bot configurado o con datos que Telegram no admite no hay enlace", () => {
    expect(followLink("falabella", "1", undefined)).toBeNull();
    expect(followLink("falabella", "1", "x y")).toBeNull();
    expect(followLink("falabella", "a.b/c", "MiBot_bot")).toBeNull();
    expect(followLink("Falabella", "1", "MiBot_bot")).toBeNull();
  });
});
