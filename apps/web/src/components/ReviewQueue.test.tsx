import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TranscriptSegment } from "../api/jobs";
import { ReviewQueue } from "./ReviewQueue";

afterEach(cleanup);

function seg(id: string, text: string, flags: string[]): TranscriptSegment {
  return {
    id,
    start_ms: 0,
    end_ms: 1000,
    text,
    edited: false,
    revision: 0,
    speaker_id: null,
    quality: { flags, avg_logprob: null },
    words: [],
  };
}

const SEGMENTS = [
  seg("a", "Normal.", []),
  seg("b", "Thank you.", ["silence_hallucination", "out_of_bounds"]),
  seg("c", "no no no no no", ["repetition"]),
  seg("d", "Quizá.", ["low_confidence"]),
];

describe("ReviewQueue", () => {
  it("cuenta solo los segmentos con flags y muestra el primero", () => {
    render(<ReviewQueue segments={SEGMENTS} onSelect={vi.fn()} />);

    expect(screen.getByRole("status").textContent).toBe(
      "3 segmentos por revisar",
    );
    expect(screen.getByText("Thank you.")).toBeTruthy();
    expect(
      screen.getByText("Posible alucinación en silencio · Fuera del audio"),
    ).toBeTruthy();
  });

  it("avisa cuando no hay nada que revisar", () => {
    render(<ReviewQueue segments={[seg("a", "Ok.", [])]} onSelect={vi.fn()} />);

    expect(screen.getByRole("status").textContent).toBe(
      "0 segmentos por revisar",
    );
    expect(screen.getByText("Ningún segmento necesita revisión.")).toBeTruthy();
  });

  it("filtra por tipo y navega con anterior/siguiente llamando onSelect", () => {
    const onSelect = vi.fn();
    render(<ReviewQueue segments={SEGMENTS} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(onSelect).toHaveBeenLastCalledWith(SEGMENTS[2]);
    fireEvent.click(screen.getByRole("button", { name: "Anterior" }));
    expect(onSelect).toHaveBeenLastCalledWith(SEGMENTS[1]);
    expect(
      (screen.getByRole("button", { name: "Anterior" }))
      .hasAttribute('disabled'),
    ).toBe(true);

    fireEvent.change(screen.getByLabelText("Tipo"), {
      target: { value: "repetition" },
    });
    expect(screen.getByRole("status").textContent).toBe("1 segmento por revisar");
    expect(screen.getByText("no no no no no")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Siguiente" }))
      .hasAttribute('disabled'),
    ).toBe(true);
  });

  it("Marcar como revisado quita el segmento y pasa al siguiente", () => {
    const onSelect = vi.fn();
    render(<ReviewQueue segments={SEGMENTS} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: "Marcar como revisado" }));

    expect(screen.getByRole("status").textContent).toBe(
      "2 segmentos por revisar",
    );
    expect(screen.queryByText("Thank you.")).toBeNull();
    expect(screen.getByText("no no no no no")).toBeTruthy();
    expect(onSelect).toHaveBeenLastCalledWith(SEGMENTS[2]);

    fireEvent.click(screen.getByRole("button", { name: "Marcar como revisado" }));
    fireEvent.click(screen.getByRole("button", { name: "Marcar como revisado" }));
    expect(screen.getByRole("status").textContent).toBe(
      "0 segmentos por revisar",
    );
    expect(screen.getByText("Todo revisado en este filtro.")).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Marcar como revisado",
        })
      ).hasAttribute('disabled'),
    ).toBe(true);
  });
});
