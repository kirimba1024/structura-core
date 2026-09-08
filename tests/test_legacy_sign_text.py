import json

import pytest
from amulet_nbt import CompoundTag, ListTag, StringTag

from structura_core.legacy_entities import restore_sign_text


def sign(messages):
    return CompoundTag({
        "front_text": CompoundTag({
            "messages": ListTag([StringTag(message) for message in messages]),
            "color": StringTag("blue"),
        }),
        "back_text": CompoundTag({"messages": ListTag([StringTag('"back"')])}),
    })


def test_restored_sign_retains_plain_text_and_json_formatting_after_shift():
    payload = sign(['{"text":""}'] * 4)
    lines = ['Welcome', '{"text":"Red","color":"red","bold":true}',
             '[{"text":"One"},{"text":"Two"}]', '"Quoted"']

    assert restore_sign_text([((0, 0, 0), 0, payload)], {(4, 5, 6): lines}, (4, 5, 6)) == 1

    assert [json.loads(str(line)) for line in payload["front_text"]["messages"]] == [
        {"text": "Welcome"}, {"text": "Red", "color": "red", "bold": True},
        [{"text": "One"}, {"text": "Two"}], "Quoted",
    ]
    assert payload["front_text"]["color"] == StringTag("blue")
    assert payload["back_text"]["messages"][0] == StringTag('"back"')


@pytest.mark.parametrize("message", [
    '"Existing"', '[{"text":"Existing"}]',
    '{"text":"","extra":[{"text":"Existing"}]}',
    '{"translate":"block.minecraft.stone"}', '{broken JSON',
])
def test_restoration_does_not_overwrite_existing_sign_content(message):
    payload = sign([message, '""', '""', '""'])
    original = payload.to_snbt()

    assert restore_sign_text([((0, 0, 0), 0, payload)], {(0, 0, 0): ["old"] * 4}, (0, 0, 0)) == 0
    assert payload.to_snbt() == original


def test_literal_braces_and_numbers_remain_readable_sign_text():
    payload = sign(['""'] * 4)
    lines = ['{unfinished', '123', 'null', '']

    restore_sign_text([((0, 0, 0), 0, payload)], {(0, 0, 0): lines}, (0, 0, 0))

    assert [json.loads(str(line)) for line in payload["front_text"]["messages"]] == [
        {"text": line} for line in lines
    ]
