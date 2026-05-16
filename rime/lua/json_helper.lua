-- json_helper.lua
-- Robust JSON encode/decode for RIME Lua environment.
-- No external dependencies; compatible with standard Lua 5.1+.

local M = {}

-- Character categories for JSON string encoding.
local ESCAPE_MAP = {
    ['"'] = '\\"',
    ['\\'] = '\\\\',
    ['\b'] = '\\b',
    ['\f'] = '\\f',
    ['\n'] = '\\n',
    ['\r'] = '\\r',
    ['\t'] = '\\t',
}

-- Encode a Lua string into a JSON string literal (with surrounding quotes).
function M.encode_string(s)
    if s == nil then
        return '""'
    end
    s = tostring(s)
    local parts = {}
    table.insert(parts, '"')
    local i = 1
    local n = #s
    while i <= n do
        local c = s:sub(i, i)
        local mapped = ESCAPE_MAP[c]
        if mapped then
            table.insert(parts, mapped)
            i = i + 1
        elseif c:byte() < 0x20 then
            -- Other control characters (0x00-0x1F except those handled above)
            table.insert(parts, string.format("\\u%04x", c:byte()))
            i = i + 1
        else
            table.insert(parts, c)
            i = i + 1
        end
    end
    table.insert(parts, '"')
    return table.concat(parts)
end

-- Recursively encode a Lua value into a JSON string.
-- Supported: nil, boolean, number, string, table (array or object).
-- For tables: if keys are all integers starting from 1, encode as array;
-- otherwise encode as object. Non-string keys are converted to strings.
function M.encode(value)
    local t = type(value)
    if value == nil then
        return "null"
    elseif t == "boolean" then
        return value and "true" or "false"
    elseif t == "number" then
        -- JSON does not support NaN/Inf; map them to null.
        if value ~= value then
            return "null"
        end
        if value == math.huge or value == -math.huge then
            return "null"
        end
        return tostring(value)
    elseif t == "string" then
        return M.encode_string(value)
    elseif t == "table" then
        -- Determine if table looks like an array.
        local maxn = 0
        local is_array = true
        for k, _ in pairs(value) do
            if type(k) ~= "number" or k ~= math.floor(k) or k < 1 then
                is_array = false
                break
            end
            if k > maxn then
                maxn = k
            end
        end
        if is_array then
            -- Sparse arrays: still encode as array, leaving gaps as null.
            local parts = {}
            for i = 1, maxn do
                if value[i] == nil then
                    table.insert(parts, "null")
                else
                    table.insert(parts, M.encode(value[i]))
                end
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            -- Object
            local parts = {}
            for k, v in pairs(value) do
                table.insert(parts, M.encode_string(tostring(k)) .. ":" .. M.encode(v))
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    else
        -- Functions, userdata, etc. -> null
        return "null"
    end
end

-- Simple JSON tokenizer used by decode.
-- String matching is done manually to handle escapes and multibyte UTF-8 correctly.
local TOKEN_PATTERNS = {
    { "whitespace", "^%s+" },
    { "string", '"' },
    { "number", "^%-?%d+%.?%d*" },
    { "literal", "^true" },
    { "literal", "^false" },
    { "literal", "^null" },
    { "punct", "^[%{%}%[%],:]" },
}

local function match_string(json_str, i)
    -- i points to the opening double quote.
    if json_str:sub(i, i) ~= '"' then
        return nil
    end
    local j = i + 1
    local n = #json_str
    while j <= n do
        local c = json_str:sub(j, j)
        if c == '"' then
            -- Found the closing quote.
            return json_str:sub(i, j)
        elseif c == '\\' then
            j = j + 2  -- skip escaped character
        else
            j = j + 1
        end
    end
    return nil  -- unterminated string
end

local function match_number(json_str, i)
    -- Match a JSON number: optional minus, digits, optional fraction, optional exponent.
    local n = #json_str
    local j = i
    if json_str:sub(j, j) == '-' then
        j = j + 1
    end
    if j > n then return nil end
    -- Integer part: at least one digit.
    local start = j
    while j <= n and json_str:sub(j, j):match("%d") do
        j = j + 1
    end
    if j == start then return nil end  -- no digits
    -- Optional fraction.
    if j <= n and json_str:sub(j, j) == '.' then
        j = j + 1
        local frac_start = j
        while j <= n and json_str:sub(j, j):match("%d") do
            j = j + 1
        end
        if j == frac_start then return nil end  -- digit required after .
    end
    -- Optional exponent.
    if j <= n and json_str:sub(j, j):match("[eE]") then
        j = j + 1
        if j <= n and json_str:sub(j, j):match("[%+%-]") then
            j = j + 1
        end
        local exp_start = j
        while j <= n and json_str:sub(j, j):match("%d") do
            j = j + 1
        end
        if j == exp_start then return nil end  -- digit required after [eE]
    end
    return json_str:sub(i, j - 1)
end

local function tokenize(json_str)
    local tokens = {}
    local i = 1
    local n = #json_str
    while i <= n do
        local matched = false
        local ch = json_str:sub(i, i)

        -- Try string and number first (manual match for complex patterns).
        if ch == '"' then
            local m = match_string(json_str, i)
            if m then
                table.insert(tokens, { type = "string", value = m, pos = i })
                i = i + #m
                matched = true
            end
        elseif ch:match("%d") or ch == '-' then
            local m = match_number(json_str, i)
            if m then
                table.insert(tokens, { type = "number", value = m, pos = i })
                i = i + #m
                matched = true
            end
        end

        if not matched then
            for _, pat in ipairs(TOKEN_PATTERNS) do
                if pat[1] == "string" or pat[1] == "number" then
                    -- Already handled above.
                else
                    local m = json_str:match(pat[2], i)
                    if m then
                        if pat[1] ~= "whitespace" then
                            table.insert(tokens, { type = pat[1], value = m, pos = i })
                        end
                        i = i + #m
                        matched = true
                        break
                    end
                end
            end
        end

        if not matched then
            error("json_helper: invalid token at position " .. i .. ": " .. json_str:sub(i, i))
        end
    end
    return tokens
end

-- Decode a JSON string literal (without surrounding quotes).
-- Handles all standard escapes including \uXXXX.
local function decode_string_literal(s)
    local out = {}
    local i = 1
    local n = #s
    while i <= n do
        local c = s:sub(i, i)
        if c == "\\" then
            local nxt = s:sub(i + 1, i + 1)
            if nxt == '"' then
                table.insert(out, '"')
                i = i + 2
            elseif nxt == "\\" then
                table.insert(out, "\\")
                i = i + 2
            elseif nxt == "/" then
                table.insert(out, "/")
                i = i + 2
            elseif nxt == "b" then
                table.insert(out, "\b")
                i = i + 2
            elseif nxt == "f" then
                table.insert(out, "\f")
                i = i + 2
            elseif nxt == "n" then
                table.insert(out, "\n")
                i = i + 2
            elseif nxt == "r" then
                table.insert(out, "\r")
                i = i + 2
            elseif nxt == "t" then
                table.insert(out, "\t")
                i = i + 2
            elseif nxt == "u" then
                local hex = s:sub(i + 2, i + 5)
                if hex and hex:match("^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$") then
                    local code = tonumber(hex, 16)
                    if code < 0x80 then
                        table.insert(out, string.char(code))
                    elseif code < 0x800 then
                        table.insert(out, string.char(
                            0xC0 + math.floor(code / 0x40),
                            0x80 + (code % 0x40)
                        ))
                    else
                        table.insert(out, string.char(
                            0xE0 + math.floor(code / 0x1000),
                            0x80 + math.floor((code % 0x1000) / 0x40),
                            0x80 + (code % 0x40)
                        ))
                    end
                    i = i + 6
                else
                    error("json_helper: invalid unicode escape at position " .. i)
                end
            else
                -- Unknown escape: pass through literally.
                table.insert(out, nxt)
                i = i + 2
            end
        else
            table.insert(out, c)
            i = i + 1
        end
    end
    return table.concat(out)
end

-- Recursive decoder.
local function parse_value(tokens, idx)
    local tok = tokens[idx]
    if not tok then
        error("json_helper: unexpected end of input")
    end

    if tok.type == "literal" then
        if tok.value == "true" then
            return true, idx + 1
        elseif tok.value == "false" then
            return false, idx + 1
        elseif tok.value == "null" then
            return nil, idx + 1
        end
    elseif tok.type == "number" then
        return tonumber(tok.value), idx + 1
    elseif tok.type == "string" then
        -- tok.value is the full string literal including quotes, e.g. "hello" or "\"esc\""
        local raw = tok.value:sub(2, -2)  -- strip surrounding quotes
        local decoded = decode_string_literal(raw)
        return decoded, idx + 1
    elseif tok.value == "[" then
        -- Array
        local arr = {}
        idx = idx + 1
        if tokens[idx] and tokens[idx].value == "]" then
            return arr, idx + 1
        end
        while true do
            local val
            val, idx = parse_value(tokens, idx)
            table.insert(arr, val)
            if tokens[idx] and tokens[idx].value == "]" then
                idx = idx + 1
                break
            elseif tokens[idx] and tokens[idx].value == "," then
                idx = idx + 1
            else
                error("json_helper: expected ',' or ']' in array")
            end
        end
        return arr, idx
    elseif tok.value == "{" then
        -- Object
        local obj = {}
        idx = idx + 1
        if tokens[idx] and tokens[idx].value == "}" then
            return obj, idx + 1
        end
        while true do
            local key_tok = tokens[idx]
            if not key_tok or key_tok.type ~= "string" then
                error("json_helper: expected string key in object")
            end
            local key
            key, idx = parse_value(tokens, idx)
            if not (tokens[idx] and tokens[idx].value == ":") then
                error("json_helper: expected ':' after object key")
            end
            idx = idx + 1
            local val
            val, idx = parse_value(tokens, idx)
            obj[key] = val
            if tokens[idx] and tokens[idx].value == "}" then
                idx = idx + 1
                break
            elseif tokens[idx] and tokens[idx].value == "," then
                idx = idx + 1
            else
                error("json_helper: expected ',' or '}' in object")
            end
        end
        return obj, idx
    else
        error("json_helper: unexpected token '" .. tok.value .. "' at position " .. tok.pos)
    end
end

-- Decode a JSON string into a Lua value.
-- Returns the value, or nil and an error message on failure.
function M.decode(json_str)
    if json_str == nil or json_str == "" then
        return nil, "json_helper: empty input"
    end
    local ok, tokens = pcall(tokenize, json_str)
    if not ok then
        return nil, tokens
    end
    local ok2, result, next_idx = pcall(parse_value, tokens, 1)
    if not ok2 then
        return nil, result
    end
    return result, nil
end

-- Convenience: decode and assert success.
function M.decode_assert(json_str)
    local result, err = M.decode(json_str)
    if err then
        error(err)
    end
    return result
end

-- Convenience: encode a JSON object from a Lua table.
function M.encode_object(tbl)
    return M.encode(tbl)
end

return M
