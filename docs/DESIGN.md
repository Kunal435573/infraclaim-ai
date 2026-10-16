# Interface direction

InfraClaim is an operations product for data-center teams pursuing service credits after vendor SLA incidents. The UI presents a case file, not an AI spectacle: the contract, incident, evidence, proposed amount, policy checks, and human decision are the main objects.

The application has one navigation system and three destinations:

1. **Overview**: see the case register, current state, evidence, policy checks, timeline, and simulated next action.
2. **Open a case**: save or select a cooling-SLA contract, then enter an incident. The form reveals the incident only after a contract is selected. Every operator-entered case goes to human review.
3. **Review queue**: inspect the contract clause and evidence, record approval for simulation, request information, or reject. Approval leads back to the exact case.

The visual system follows the [UI/UX Pro Max skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill): restrained Swiss-style hierarchy, quiet neutral surfaces, trust-blue actions, explicit status text, and low motion. Segoe UI is used as an available system font so the local application renders without an external font request. Color is paired with text for every state. Forms have persistent labels; navigation, actions, and focus states support keyboard use. The layout switches from a sidebar to top navigation on smaller screens.

The interface deliberately distinguishes a **live configured inference service** from a successful per-case inference, and **simulated vendor/credit steps** from real recovery. Model scores are marked uncalibrated.
