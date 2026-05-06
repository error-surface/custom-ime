local socket_path = os.getenv("HOME") .. "/.local/share/custom-ime/ranker.sock"

local function send_fire_and_forget(request_json)
    os.execute(string.format(
        "echo '%s' | nc -U '%s' -w 1 &>/dev/null &",
        request_json:gsub("'", "'\\''"),
        socket_path
    ))
end

local function select_notifier(env)
    env.notifier = env.engine.context.select_notifier:connect(function(ctx)
        local text = ctx:get_commit_text()
        if not text or #text == 0 then
            return
        end
        local pinyin = ctx.input or ""
        local request = string.format(
            '{"action":"select","pinyin":"%s","context":"","chosen":"%s","candidates":[],"position":0}',
            pinyin, text
        )
        send_fire_and_forget(request)
    end)
end

local function fini(env)
    if env.notifier then
        env.notifier:disconnect()
    end
end

return { init = select_notifier, func = function() end, fini = fini }
