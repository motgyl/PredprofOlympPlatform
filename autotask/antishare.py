def modify(uuid, flag: str, mode: str = "normal", salt: str = "") -> str:
    from hashlib import sha512
    match mode:
        case "register":
            wrapper, body = flag[:flag.index("{") + 1], flag[flag.index("{") + 1:-1]
            hash = sha512((uuid + salt).encode()).hexdigest()
            hash = hash * (len(body) // len(hash) + 1)
            modified_flag = ""
            for i in range(len(body)):
                if int(hash[i], 16) % 2:
                    modified_flag += body[i].upper()
                else:
                    modified_flag += body[i].lower()
            return wrapper + modified_flag + "}"
        case "leetspeak":
            leetspeak_dict = {
                'a': '4',
                'e': '3', 
                'i': '1', 
                'o': '0', 
                's': '5', 
                't': '7'
            }
            wrapper, body = flag[:flag.index("{") + 1], flag[flag.index("{") + 1:-1]
            hash = sha512((uuid + salt).encode()).hexdigest()
            hash = hash * (len(body) // len(hash) + 1)
            modified_flag = ""
            for i in range(len(body)):
                if int(hash[i], 16) % 3 == 0:
                    if body[i].lower() in leetspeak_dict:
                        modified_flag += leetspeak_dict[body[i].lower()]
                    else:
                        modified_flag += body[i]
                elif int(hash[i], 16) % 3 == 1:
                    modified_flag += body[i].lower()
                else:
                    modified_flag += body[i].upper()
            return wrapper + modified_flag + "}"
        case "normal":
            return flag
        case _:
            raise ValueError(f"Unknown mode: {mode}")
        
        
# print(modify("123e4567-e89b-12d3-a456-426614174001", "bobr{s0m3_l0ng_t3st_fl4g}", mode="register", salt="salt"))
print(modify("123e4567-e89b-12d3-a456-426614174000", "bobr{some_long_test_flag}", mode="leetspeak", salt="salt"))