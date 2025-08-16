flowchart TD
%% Define Styles
classDef startend fill:#B0BEC5,stroke:#333,stroke-width:1px,color:#000
classDef demand fill:#FFD54F,stroke:#333,stroke-width:1px,color:#000
classDef location fill:#81C784,stroke:#333,stroke-width:1px,color:#000
classDef sim fill:#64B5F6,stroke:#333,stroke-width:1px,color:#000
classDef mix fill:#F06292,stroke:#333,stroke-width:1px,color:#000
classDef results fill:#4DD0E1,stroke:#333,stroke-width:1px,color:#000
classDef decision fill:#E0E0E0,stroke:#333,stroke-width:1px,color:#000

    %% Flow
    Start([Start]):::startend --> Login[Login / Register]:::sim

    %% Demand Module
    Login --> ED1[Select Projection]:::demand
    ED1 --> ED2[Create Daily Profile]:::demand
    ED2 --> ED3[Input Variability]:::demand
    ED3 --> ED4[Generate Demand Chart]:::demand

    %% Location Module
    ED4 --> L1[Select Region & Location]:::location
    L1 --> L2[View Solar/Wind Resource Data]:::location

    %% Multi-Location Decision
    L2 --> D1{Multi-Location?}:::decision
    D1 -- No --> S_single[Run Single-Location Simulation]:::sim
    D1 -- Yes --> S1[Multi-Location Config]:::sim
    S1 --> S2[Confirm Locations]:::sim
    S2 --> S3[Input Parameters]:::sim

    %% Custom Mix Decision
    S3 --> D2{Custom Energy Mix?}:::decision
    D2 -- No --> S4[Set Transmission Parameters]:::sim
    D2 -- Yes --> M1[Upload Excel File]:::mix
    M1 --> M2[Validate Excel]:::mix
    M2 --> M3[Integrate Custom Mix]:::mix
    M3 --> S4

    %% Simulation and Results
    S4 --> S5[Run Multi-Location Simulation]:::sim
    S5 --> Results[View Results: Energy, COE, Transfers]:::results

    S_single --> Results
    Results --> End([End]):::startend
