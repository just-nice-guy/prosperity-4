import { create } from "zustand";

type TimelineStore = {
  product: string;
  timestamp: number | null;
  roundNum: number | null;
  dayNum: number | null;
  setProduct: (product: string) => void;
  setTimestamp: (timestamp: number | null) => void;
  setContext: (roundNum: number | null, dayNum: number | null) => void;
};

export const useTimelineStore = create<TimelineStore>((set) => ({
  product: "EMERALDS",
  timestamp: null,
  roundNum: null,
  dayNum: null,
  setProduct: (product) => set({ product, timestamp: null }),
  setTimestamp: (timestamp) => set({ timestamp }),
  setContext: (roundNum, dayNum) => set({ roundNum, dayNum })
}));
