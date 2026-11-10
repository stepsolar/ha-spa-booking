package main

import (
	"testing"

	"go.mau.fi/whatsmeow/types"
)

func TestParseChat(t *testing.T) {
	cases := map[string]types.JID{
		"393331234567@c.us":           types.NewJID("393331234567", types.DefaultUserServer),
		"+41791234567":                types.NewJID("41791234567", types.DefaultUserServer),
		"393331234567@s.whatsapp.net": types.NewJID("393331234567", types.DefaultUserServer),
		"120363012345@g.us":           types.NewJID("120363012345", types.GroupServer),
		"123456789012345@lid":         types.NewJID("123456789012345", types.HiddenUserServer),
	}
	for raw, want := range cases {
		got, err := parseChat(raw)
		if err != nil || got != want {
			t.Errorf("parseChat(%q) = %v, %v; want %v", raw, got, err, want)
		}
	}
	for _, bad := range []string{"", "@c.us", "abc@c.us", "33x@c.us", "1@newsletter"} {
		if _, err := parseChat(bad); err == nil {
			t.Errorf("parseChat(%q) accepted", bad)
		}
	}
}

func TestChatIDSpellsPhonesLikeWAHA(t *testing.T) {
	if got := chatID(types.NewJID("393331234567", types.DefaultUserServer)); got != "393331234567@c.us" {
		t.Errorf("phone: %s", got)
	}
	if got := chatID(types.NewJID("123", types.HiddenUserServer)); got != "123@lid" {
		t.Errorf("lid: %s", got)
	}
}
