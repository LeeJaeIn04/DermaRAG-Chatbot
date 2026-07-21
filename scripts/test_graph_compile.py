from app.graph.workflow import derma_rag_graph

def main() -> None :
    if derma_rag_graph is None :
        raise AssertionError("derma_rag_graph is None")
    
    print("graph compile ok")

if __name__ == "__main__":
    main()
    