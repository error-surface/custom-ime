local json_helper = require("json_helper")

local socket_path = os.getenv("HOME") .. "/.local/share/custom-ime/ranker.sock"
local script_dir = debug.getinfo(1, "S").source:match("^@(.+)/[^/]+$") or "."
local client_script = script_dir .. "/../../scripts/ranker_client.py"

local function send_fire_and_forget(request_json)
    local cmd = string.format(
        "python3 '%s' '%s' '%s' >/dev/null 2>&1 &",
        client_script:gsub("'", "'\\''"),
        socket_path:gsub("'", "'\\''"),
        request_json:gsub("'", "'\\''")
    )
    os.execute(cmd)
end

local function select_notifier(env)
    -- env persists across calls; use it to track previous word for bigram context.
    env.prev_word = env.prev_word or ""

    env.notifier = env.engine.context.select_notifier:connect(function(ctx)
        local text = ctx:get_commit_text()
        if not text or #text == 0 then
            return
        end

        local pinyin = ctx:get_property and (ctx:get_property("custom_ime.last_pinyin") or ctx.input) or (ctx.input or "")

        -- Build candidate list from property set by rerank_filter.
        local candidates = {}
        local candidates_json = ctx:get_property and (ctx:get_property("custom_ime.last_candidates_json") or "[]") or "[]"
        local decoded, _ = json_helper.decode(candidates_json)
        if decoded and type(decoded) == "table" then
            candidates = decoded
        end

        -- Determine position of selected text in candidates.
        local pos = 0
        for i, w in ipairs(candidates) do
            if w == text then
                pos = i - 1
                break
            end
        end

        -- Context for bigram learning is the PREVIOUS committed word, not the full sentence.
        local context = env.prev_word or ""

        local request = json_helper.encode({
            action = "select",
            pinyin = pinyin,
            context = context,
            context2 = env.prev_word2 or "",
            chosen = text,
            candidates = candidates,
            position = pos,
        })
        send_fire_and_forget(request)

        -- Track second-to-last word for trigram context (before updating prev_word)
        env.prev_word2 = env.prev_word2 or ""
        if env.prev_word and env.prev_word ~= "" then
            env.prev_word2 = env.prev_word
        end

        -- Update previous word for next commit.
        env.prev_word = text

        if ctx.set_property then
            ctx:set_property("custom_ime.prev_word2", env.prev_word2 or "")
        end
    end)
end

local function fini(env)
    if env.notifier then
        env.notifier:disconnect()
    end
end

return { init = select_notifier, func = function() end, fini = fini }
