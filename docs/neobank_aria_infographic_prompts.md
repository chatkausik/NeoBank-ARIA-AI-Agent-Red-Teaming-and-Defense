# NeoBank ARIA infographic — generation prompts

Created with the built-in image-generation tool. Final image: [neobank_aria_infographic.png](neobank_aria_infographic.png).

## Initial generation

Reference: `architecture_one_page_color.png` (factual content only).

Use case: infographic-diagram.
Create a completely redesigned, visually striking, professional one-page illustrated infographic about the NeoBank ARIA project. Use the reference image ONLY as a factual content reference. Replace its text-heavy rounded-box flowchart with a polished editorial infographic with beautiful original illustrations, large expressive icons, concise labels and a clearly organized visual story. This is a finished shareable infographic, not a website mockup. Landscape 3:2 composition, high resolution, generous margins, extremely readable typography.

Art direction: warm ivory background, dark navy text, rich violet for the ARIA assistant, vivid teal/emerald for safeguards, orange/coral for the intentionally unguarded route, sky blue for the customer and data. Sophisticated vector-like editorial illustration with subtle dimensional shading. Illustrate a customer using a chat interface, a friendly abstract AI assistant core, security checkpoints, a database, a policy book, a cloud model service, and a red-team testing laboratory. Give the illustrations substantial visual presence. Avoid a grid of paragraph-filled cards. Use generous negative space, consistent hierarchy, restrained connectors with clear arrowheads, and large legible labels. No tiny paragraphs, tangled lines, decorative charts, invented scores, or claims of complete safety.

Title exact: "NeoBank ARIA"
Subtitle exact: "An AI banking assistant, tested and protected"

Upper two thirds: a clear illustrated customer-question-to-reply journey reading LEFT TO RIGHT. These exact labels accompany its five illustrated stages:
"Customer chat"
"Input + conversation checks"
"ARIA assistant"
"Output leak scan"
"Reply"
Under ARIA put: "Plan • Retrieve • Draft".
Green route label "Guarded". Make it unmistakable that input checks happen BEFORE ARIA and the output scan happens AFTER ARIA drafts.
An orange alternate route should show the same customer → same ARIA assistant → same reply while bypassing the two green checkpoints. Orange route caption: "Unguarded: skip screens, broad data access".
Small green note: "Blocked requests return a safe reply".
Both modes use the same ARIA runtime.

Connect the ARIA illustration to three compact illustrated supporting resources, clearly subordinate to the main flow:
"OpenAI API" with subtitle "Planning + answers".
"Account lookup" with subtitle "Guarded: session account only".
"Policy lookup" with subtitle "Guarded: public + redacted".
These connections must not interrupt the main reading flow. SQLite is a local fictional account database; policies are local Python content; OpenAI is external. Optional small local labels "SQLite" and "Python policies".

Bottom third: a separate, warmly tinted illustrated ribbon titled "RED-TEAM TESTING LAB", with a simple left-to-right sequence:
"43 attacks + 10 benign cases" → "Run both modes" → "Score every turn" → "Evidence + reports".
Below scoring in small but readable text: "Security • Utility • Execution • Judge status".
Below reports: "JSONL • HTML • Markdown".
This laboratory evaluates the same application; evaluation does not control customer replies.

Footer exact: "Fictional data • Demo identity • Read-only tools • Review is a static message".
Keep all spelling correct, all content inside the canvas, and ensure a visually balanced infographic that can be understood in seconds.

## Refinement

Reference: initial generated infographic.

Refine this infographic in place. Preserve its landscape layout, title, subtitle, colorful illustration style, customer, assistant robot, green checkpoints, supporting resources, and testing ribbon. Make these targeted corrections:
1. CRITICAL: the orange Unguarded route must visibly enter the SAME purple ARIA assistant and then leave it on a second orange arrow to Reply. It may bypass the green Input checkpoint and green Output checkpoint, but must NEVER draw a continuous customer-to-reply shortcut under the robot. Split the orange route into TWO clearly separate arrow segments: Customer → ARIA and ARIA → Reply, with a gap under the assistant and no connecting line through that gap. Place the existing orange mode caption where it doesn't obscure these arrows. Keep the normal green Customer → Input checks → ARIA → Output scan → Reply path.
2. Keep the green early-return branch and caption "Blocked requests return a safe reply".
3. Under "ARIA assistant", use exactly "Plan • Retrieve if needed • Draft"; use two lines if needed so text remains large.
4. Replace the sample monetary answer with a neutral chat reply: "Here are your account details." No dollar amount.
5. Remove the four decorative marketing/slogan texts completely: the handwritten "Safer Banking Together" near the top, "PEOPLE TECHNOLOGY TRUST", the handwritten lower-left "Helpful Answers Safer Systems Brighter Banking", and the "GOOD QUESTIONS SAFER OUTCOMES" placard. Remove the handwritten "Test Learn Improve" at the testing ribbon. Keep the remaining space elegantly airy; retain the tasteful bank skyline background, with no new text or fillers.
6. Keep "Same ARIA runtime in both modes" visible as an architectural note, not a slogan.
7. Under Reply remove the generic "Return directly" caption because the routes already explain the behavior; use "Answer or safe refusal" instead.
Everything else, especially exact factual testing counts, lab scoring dimensions, and footer, stays unchanged. All arrows must be unambiguous and all labels legible.
