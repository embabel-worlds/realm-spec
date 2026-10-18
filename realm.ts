// Written by shinar realm migrate from realm.yml.
// Note: left out realm.yml field category: realm.ts has no field for it.
import { type Realm } from "@embabel/realm-types";

export default {
  name: "spec",
  version: "0.2.0",
  description: "The Embabel Realm specification (README.md is the contract) plus a `realm-authoring` Agent Skill that guides an assistant through creating and extending realms — directory layout, declarative-vs-handlers, types, APIs, virtual-join producers (RemoteRepositories) with predicate pushdown and pagination, functions, events, skills, and the hard rules. Install this realm to get realm-authoring help in chat.",
  author: "Embabel",
  url: "https://github.com/embabel/realm-spec",
  tags: ["meta", "developer-tools", "skills"],
} satisfies Realm;
