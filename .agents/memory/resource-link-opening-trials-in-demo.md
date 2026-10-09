# Resource link opening trials live in the Objectives demo

The user prefers a resource to open over Lab without iframe problems and asked
to try the opening options quickly in the Objectives demo before choosing the
production behavior. Its header now offers an editable URL, Example site,
GitHub and Google Docs examples, and Pop-out over Lab / Inside Lab / Browser tab.

Pop-out uses a synchronous client-side window.open with popup size/position
features and noopener,noreferrer. It loads the actual page directly. Chrome
controls the frame and final placement; this is a separate window, not an
iframe-free browser tab inside the web app. The floating Inside Lab preview
still uses an iframe and retains framing/login restrictions.

Explicit trials may open real sites. The demo parent sandbox permits popups
to escape its sandbox so they can sign in normally; it still omits same-origin
access. The demo CSP permits HTTP(S) frames but keeps connect-src 'none'.
Existing fictional resource links, simulated sessions and workspace APIs keep
their demo behavior. This refines objectives-demo-is-browser-only.md only for
the explicit trial controls; production link defaults have not changed.
