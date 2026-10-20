# Access control

The seat's RF protocol has **no authentication**: anyone who can transmit at 433.9 MHz can run the seat.
A Home Assistant integration that simply exposes "Rear", "Dry" and the sliders would let *anyone with access
to the dashboard, a voice assistant or an automation* start a wash while somebody is sitting on the seat.

This project guards against that inside the ESP32 (so the dashboard, automations and voice assistants cannot
bypass it).

## The lock

* The controls start **locked** at every boot. While locked, every command except **Stop** is ignored (logged
  as `Locked: ignoring key 0x..`), and the level sliders refuse to change.
* **Any valid button press on the real remote** unlocks them. A valid press is a packet with the right header
  and checksum, so noise cannot unlock. This means the person must be physically holding the remote, which
  lives in the toilet, in radio range.
* They stay unlocked until **3 minutes after the most recent activity**: a button on the real remote, or a
  change accepted from Home Assistant. Each one restarts the 3-minute window. A wash cycle lasts about two
  minutes, so you can start a wash on the remote and adjust it from Home Assistant without re-unlocking.
* **Stop from Home Assistant is never blocked**, so a stuck or unwanted function can always be ended.
* A **Lock Controls** button re-locks immediately.
* Action buttons (Rear, Female, Dry, Self clean, Swing, Massage) are **rate-limited to one per second**.
* Level changes can only be sent for the **function in use** (the one last started on the remote or from Home
  Assistant); other functions' sliders just store the new value for next time. This stops a slider for Female
  from changing a running Rear wash, because the radio packet does not say which function it is for.

Entities for the dashboard: `Controls Unlocked` (binary sensor), `Unlock Time Remaining` (seconds),
`Last Remote Button`, `Remote Packets Heard`, and the `Lock Controls` button.

## Away mode (the one deliberate bypass)

`Seat Heat Away Mode` (a switch) lets an automation turn the seat heater **off** while nobody is home, and put
it back as soon as somebody returns, even while the controls are locked:

* **On**: remembers the current heater level (it is stored in flash, so a reboot while away is safe), sends
  "heater off" and shows 0 on the slider.
* **Off**: restores the remembered level, but only if the heater is still off (if somebody changed it with the
  remote in the meantime it is left alone).
* The command is sent twice, 5 seconds apart, in case the seat misses one.

It can only ever turn the heater off or put it back where it was; it can't start a wash or change anything
else. [`home-assistant/away-automation.yaml`](../home-assistant/away-automation.yaml) drives it from a
presence sensor.

## Limits

* It is a **household** safeguard, not security: it does nothing about someone with a 433 MHz transmitter, or
  about the physical remote.
* Reception of the remote is not perfect. If a press does not unlock, press again.
* The lock lives in the ESP32. If it reboots the controls lock again until the next remote press.
