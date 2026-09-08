import re

SCENE_PATH = '/home/timothy/orca/Mate-Engine-Linux-Port/Assets/MATE ENGINE - Scenes/Mate Engine Main.unity'

with open(SCENE_PATH, 'r') as f:
    lines = f.readlines()

in_gameobject = False
target_name = None
modified = False

for i in range(len(lines)):
    line = lines[i]
    
    # Start of a GameObject block
    if line.startswith('GameObject:'):
        in_gameobject = True
        target_name = None
        continue
        
    if in_gameobject:
        # Check name
        match = re.match(r'^  m_Name: (.+)$', line)
        if match:
            target_name = match.group(1).strip()
            
        # Check active status
        match_active = re.match(r'^  m_IsActive: (\d)$', line)
        if match_active:
            if target_name == 'ChooseEngine' and match_active.group(1) == '1':
                lines[i] = '  m_IsActive: 0\n'
                print("Patched ChooseEngine to inactive.")
                modified = True
            elif target_name == 'ChatOllama' and match_active.group(1) == '0':
                lines[i] = '  m_IsActive: 1\n'
                print("Patched ChatOllama to active.")
                modified = True
                
    # Reset if we hit a new document
    if line.startswith('---'):
        in_gameobject = False
        target_name = None

if modified:
    with open(SCENE_PATH, 'w') as f:
        f.writelines(lines)
    print("Scene patched successfully.")
else:
    print("No changes made. Targets might already be patched or not found.")

