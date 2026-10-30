# Focus: the user interface

The module as a person uses it in Basecamp. Cover every item in
/run/inventory.json (the UI files and every method the UI can call), and
every screen and feature: list each one in /run/src/coverage.json as
`screen:<name>` with what you did there and its `desk shot`.

For each screen and feature:
- **Does it work?** Use it as a person would, end to end: create, join,
  answer, edit, export, settings. Note what fails, freezes, or misleads.
- **What it shows:** whether what the screen says is true (states,
  confirmations, "verified", errors); what it hides that a person needs.
- **Hostile input through the UI:** huge, empty, malformed, unicode tricks,
  markup and injection strings in every field; content from others (names,
  titles, answers) rendered on this screen.
- **Mistakes a person can make:** destructive actions without confirmation,
  irreversible steps, lost work, secrets shown or copied.
- **Accessibility and clarity** where it gets in the way of use.

Screenshots are the evidence: one per screen and per finding.
