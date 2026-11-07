/*
 * A realm.ts realm with no YAML beside it: one evaluated definition declaring a type. The
 * validator evaluates it as the host will, so it passes under strict only when realm.ts is read.
 */
import type { Realm } from "@embabel/realm-types";

export default {
  name: "realm-gadgets",
  version: "0.1.0",
  description: "A fixture realm declared in realm.ts.",
  types: {
    Gadget: {
      description: "A gadget, keyed by its serial number.",
      properties: {
        serial: { identity: true, description: "The gadget's serial number." },
        name: "What the gadget is called.",
      },
    },
  },
} satisfies Realm;
