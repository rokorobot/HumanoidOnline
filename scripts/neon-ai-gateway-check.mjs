// Smoke test for the Neon AI Gateway. Run: node --env-file=.env.local scripts/neon-ai-gateway-check.mjs
import { neon } from "@neon/ai-sdk-provider";
import { generateText } from "ai";

const { text } = await generateText({
  model: neon("claude-haiku-4-5"),
  prompt: "In one short sentence, what is a humanoid robot?",
});
console.log(text);
