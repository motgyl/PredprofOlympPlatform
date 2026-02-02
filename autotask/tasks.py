from examples import Challenge, SimpleStegano


sainity = Challenge()
sainity.description = "Sainity check, your flag is: {flag}"
sainity.generate("bobr{t3st_s41n1ty}")

print(sainity.get_info())
# stega = SimpleStegano(image_path="frame.png")
# stega.generate(flag="bobr{st3g4n0_1s_3asy_2}", save_path="images/user2/")
# print(stega.get_info())