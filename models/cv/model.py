import torch
import torch.nn as nn
import timm

class MultiTaskDefectModel(nn.Module):
    def __init__(self, num_grades=4, num_defects=5, mvtec_weights_path=None):
        super().__init__()
        
        # 1. Initialize the ViT architecture
        self.backbone = timm.create_model('vit_base_patch16_224', pretrained=False)
        
        # 2. Load custom MVTec_AD trained weights
        if mvtec_weights_path:
            print(f"Loading custom MVTec backbone weights from: {mvtec_weights_path}")
            checkpoint = torch.load(mvtec_weights_path, map_location='cpu')
            if isinstance(checkpoint, dict) and "backbone_state_dict" in checkpoint:
                mvtec_state_dict = checkpoint["backbone_state_dict"]
            else:
                mvtec_state_dict = checkpoint
            
            mvtec_state_dict = {k: v for k, v in mvtec_state_dict.items() if not k.startswith('head')}
            self.backbone.load_state_dict(mvtec_state_dict, strict=False)
            print("MVTec backbone loaded successfully!")
        else:
            print("Warning: No MVTec weights provided. Using random initialization.")

        # 3. Remove the original classification head
        self.feature_dim = self.backbone.head.in_features
        self.backbone.head = nn.Identity() 
        
        # 4. Tête 1 : Grading (A/B/C/D)
        self.grade_head = nn.Sequential(
            nn.Linear(self.feature_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_grades)
        )
        
        # 5. Tête 2 : Defect Detection (Multi-Label)
        self.defect_head = nn.Sequential(
            nn.Linear(self.feature_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, num_defects)
        )

    def forward(self, x):
        features = self.backbone(x)
        grade_logits = self.grade_head(features)
        defect_logits = self.defect_head(features)
        return grade_logits, defect_logits